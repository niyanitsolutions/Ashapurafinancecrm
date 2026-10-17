"""Engine execution is substituted; WAV parsing/checksums and queue logic are real."""

import hashlib
import io
import json
import struct
import sys
import wave
from datetime import timedelta

import pytest
import httpx

from app.core.exceptions import ForbiddenError, NotFoundError
from app.features.auth.models import User
from app.features.voice_assistant import speech_jobs, speech_runtime
from app.features.voice_assistant import conversation
from app.features.voice_assistant.conversation import ConversationConfig
from app.features.voice_assistant.platform_schemas import ComponentChange
from app.features.voice_assistant.platform_service import PlatformService, ensure_platform_indexes
from app.features.voice_assistant.speech_jobs import SpeechJobs, ensure_speech_job_indexes
from app.features.voice_assistant.speech_runtime import LocalSpeechRuntime, SpeechConfig, SpeechProfile, asset, verify, wav_metadata
from app.utils.datetime import utc_now


def sample_wav(*, rate=16000, silent=False):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes((b"\0\0" if silent else struct.pack("<h", 1024)) * rate)
    return buffer.getvalue()


@pytest.fixture
def speech_config(tmp_path, monkeypatch):
    binary = tmp_path / "test-binary-not-executable"
    model = tmp_path / "model.bin"
    sample = tmp_path / "reference.wav"
    binary.write_bytes(b"synthetic binary checksum fixture")
    model.write_bytes(b"synthetic model checksum fixture")
    sample.write_bytes(sample_wav())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    profile = SpeechProfile(kind="stt", engine="whisper_cpp", executable=str(binary), executable_sha256=digest(binary), model="model.bin", model_sha256=digest(model), language="en", version="fixture-only", license_reference="fixture license review", sample="reference.wav", sample_sha256=digest(sample), expected_transcript="This is a reference test.")
    cfg = SpeechConfig(_env_file=None, root=str(tmp_path), profiles={"test-stt": profile})
    monkeypatch.setattr(speech_jobs, "get_speech_config", lambda: cfg)
    monkeypatch.setattr(speech_runtime, "get_speech_config", lambda: cfg)
    return cfg


@pytest.fixture
async def speech_context(mock_db, owner_headers, speech_config):
    await ensure_platform_indexes(mock_db)
    await ensure_speech_job_indexes(mock_db)
    actor = User.model_validate(await mock_db.users.find_one({"role": "owner"}))
    svc = PlatformService(mock_db)
    state = await svc.status("test", actor)
    state = await svc.component("test", "workers", ComponentChange(version=state["version"], enabled=True, reason="Local verification worker"), actor)
    await svc.component("test", "stt", ComponentChange(version=state["version"], enabled=True, profile_id="test-stt", reason="Reference audio test"), actor)
    return SpeechJobs(mock_db), svc, actor, speech_config


def test_real_wav_decode_rejects_silence_truncation_and_wrong_rate():
    assert wav_metadata(sample_wav(), reference=True)["duration_seconds"] == 1
    for audio in (sample_wav(silent=True), sample_wav()[:-2], sample_wav(rate=8000), b"not-a-wave" * 10):
        with pytest.raises(ValueError):
            wav_metadata(audio, reference=True)


def test_reference_normalization_preserves_indic_vowels_and_unicode_equivalence():
    assert speech_runtime.normalize_text("कल") != speech_runtime.normalize_text("कला")
    assert speech_runtime.normalize_text("café") == speech_runtime.normalize_text("cafe\u0301")


def test_asset_paths_and_integrity_are_enforced(speech_config, tmp_path):
    model = asset(str(tmp_path), "model.bin")
    verify(model, speech_config.profiles["test-stt"].model_sha256)
    with pytest.raises(ValueError):
        verify(model, "0" * 64)
    with pytest.raises((ValueError, FileNotFoundError)):
        asset(str(tmp_path), "../outside-model.bin")
    with pytest.raises(ValueError):
        asset(str(tmp_path), str(model))


async def test_whisper_invocation_and_reference_match(speech_config, monkeypatch):
    calls = []
    async def fake_execute(command, directory, timeout, memory):
        calls.append(command)
        (directory / "result.txt").write_text("This is a reference test.")
    monkeypatch.setattr(speech_runtime, "execute", fake_execute)
    evidence, audio = await LocalSpeechRuntime(speech_config).test("test-stt")
    assert audio is None and evidence["reference_transcription_matched"]
    assert "-otxt" in calls[0] and "-ng" in calls[0]
    assert calls[0][0] == speech_config.profiles["test-stt"].executable


async def test_wrong_transcription_is_not_a_pass(speech_config, monkeypatch):
    async def fake_execute(command, directory, timeout, memory):
        (directory / "result.txt").write_text("Incorrect reference words")
    monkeypatch.setattr(speech_runtime, "execute", fake_execute)
    with pytest.raises(ValueError, match="does not match"):
        await LocalSpeechRuntime(speech_config).test("test-stt")


async def test_model_checksum_failure_never_runs_engine(speech_config, monkeypatch):
    async def forbidden(*args):
        pytest.fail("Integrity failure must not execute a process")
    monkeypatch.setattr(speech_runtime, "execute", forbidden)
    speech_config.profiles["test-stt"].model_sha256 = "0" * 64
    with pytest.raises(ValueError, match="integrity"):
        await LocalSpeechRuntime(speech_config).test("test-stt")


async def test_job_worker_persists_minimal_evidence_no_transcript(speech_context, mock_db, monkeypatch):
    jobs, _, actor, _ = speech_context
    async def fake_execute(command, directory, timeout, memory):
        (directory / "result.txt").write_text("This is a reference test.")
    monkeypatch.setattr(speech_runtime, "execute", fake_execute)
    job = await jobs.submit("test", "test-stt", actor)
    assert job["status"] == "queued"
    assert await jobs.sweep() == 1
    result = (await jobs.list("test", actor))["items"][0]
    assert result["status"] == "passed" and result["evidence"]["integrity_verified"]
    assert "reference test" not in str(await mock_db.voice_speech_jobs.find({}).to_list(None)).lower()
    assert (await jobs.list("production", actor))["total"] == 0


async def test_disable_during_job_discards_evidence(speech_context, monkeypatch):
    jobs, controls, actor, _ = speech_context
    async def fake_test(self, profile):
        state = await controls.status("test", actor)
        await controls.component("test", "stt", ComponentChange(version=state["version"], enabled=False, profile_id="test-stt", reason="Disable while testing"), actor)
        return {"fake": True}, None
    monkeypatch.setattr(LocalSpeechRuntime, "test", fake_test)
    await jobs.submit("test", "test-stt", actor)
    await jobs.sweep()
    job = (await jobs.list("test", actor))["items"][0]
    assert job["status"] == "superseded" and job["evidence"] is None


async def test_interrupted_jobs_are_not_automatically_retried(speech_context, mock_db):
    jobs, _, actor, _ = speech_context
    await jobs.submit("test", "test-stt", actor)
    await mock_db.voice_speech_jobs.update_one({}, {"$set": {"status": "running", "lease_token": "dead-worker"}})
    assert await jobs.sweep() == 0
    assert (await jobs.list("test", actor))["items"][0]["status"] == "interrupted"


async def test_queue_deadline_failure_and_safe_errors(speech_context, mock_db):
    jobs, _, actor, _ = speech_context
    await jobs.submit("test", "test-stt", actor)
    await mock_db.voice_speech_jobs.update_one({}, {"$set": {"queue_deadline": utc_now() - timedelta(seconds=1)}})
    assert await jobs.sweep() == 0
    assert (await jobs.list("test", actor))["items"][0]["status"] == "expired"


async def test_disabled_profiles_and_unknown_profile_denied(speech_context):
    jobs, _, actor, _ = speech_context
    with pytest.raises(NotFoundError):
        await jobs.submit("test", "not-approved", actor)
    with pytest.raises(ForbiddenError):
        await jobs.submit("production", "test-stt", actor)


async def test_speech_http_permissions_and_catalog_redaction(client, owner_headers, employee_headers, speech_config):
    root = "/api/v1/voice-assistant/platform"
    result = await client.get(root + "/speech-profiles", headers=owner_headers)
    assert result.status_code == 200 and "executable" not in result.text and speech_config.root not in result.text
    assert (await client.get(root + "/speech-profiles", headers=employee_headers)).status_code == 403
    assert (await client.post(root + "/test/speech-tests/test-stt", headers=employee_headers)).status_code == 403
    assert (await client.get(root + "/test/speech-tests/invalid/audio", headers=owner_headers)).status_code == 404


def add_tts(cfg):
    from pathlib import Path
    root = Path(cfg.root)
    (root / "voice.onnx").write_bytes(b"synthetic ONNX fixture")
    (root / "voice.onnx.json").write_text("{}")
    stt = cfg.profiles["test-stt"]
    cfg.profiles["test-tts"] = SpeechProfile(kind="tts", engine="piper", executable=stt.executable, executable_sha256=stt.executable_sha256, model="voice.onnx", model_sha256=hashlib.sha256((root / "voice.onnx").read_bytes()).hexdigest(), config_sha256=hashlib.sha256(b"{}").hexdigest(), language="en", version="fixture-only", license_reference="fixture license review")


async def test_piper_output_decodes_and_audio_is_private(speech_context, mock_db, monkeypatch):
    jobs, controls, actor, cfg = speech_context
    add_tts(cfg)
    state = await controls.status("test", actor)
    await controls.component("test", "tts", ComponentChange(version=state["version"], enabled=True, profile_id="test-tts", reason="Local synthesis verification"), actor)
    async def fake_execute(command, directory, timeout, memory):
        assert command[1:4] == ["-I", "-m", "piper"]
        (directory / "result.wav").write_bytes(sample_wav(rate=22050))
    monkeypatch.setattr(speech_runtime, "execute", fake_execute)
    job = await jobs.submit("test", "test-tts", actor)
    await jobs.sweep()
    public = (await jobs.list("test", actor))["items"][0]
    assert public["status"] == "passed" and public["evidence"]["sample_rate"] == 22050
    assert "audio_encrypted" not in public
    stored = await mock_db.voice_speech_jobs.find_one({})
    assert stored["audio_encrypted"] and "RIFF" not in stored["audio_encrypted"]
    assert wav_metadata(await jobs.audio("test", job["id"], actor))["channels"] == 1
    with pytest.raises(NotFoundError):
        await jobs.audio("production", job["id"], actor)
    await mock_db.voice_speech_jobs.update_one({}, {"$set": {"expires_at": utc_now() - timedelta(seconds=1)}})
    with pytest.raises(NotFoundError):
        await jobs.audio("test", job["id"], actor)


async def test_pipeline_runs_stt_structured_inference_tts_contract(speech_context, monkeypatch):
    jobs, controls, actor, cfg = speech_context
    add_tts(cfg)
    ai = ConversationConfig(_env_file=None, local_ai_enabled=True, local_ai_model="fixture-local-model")
    monkeypatch.setattr(conversation, "get_conversation_config", lambda: ai)
    monkeypatch.setattr(speech_jobs, "get_conversation_config", lambda: ai)
    state = await controls.status("test", actor)
    state = await controls.component("test", "tts", ComponentChange(version=state["version"], enabled=True, profile_id="test-tts", reason="Local pipeline verification"), actor)
    await controls.component("test", "inference", ComponentChange(version=state["version"], enabled=True, reason="Local pipeline inference"), actor)
    calls = []
    async def fake_execute(command, directory, timeout, memory):
        if "-otxt" in command:
            calls.append("stt")
            (directory / "result.txt").write_text("This is a reference test.")
        else:
            calls.append("tts")
            assert (directory / "sample.txt").read_text().strip() == "Would you like to speak to a member of staff?"
            (directory / "result.wav").write_bytes(sample_wav(rate=22050))
    monkeypatch.setattr(speech_runtime, "execute", fake_execute)
    original = httpx.AsyncClient
    def model(request):
        calls.append("inference")
        assert request.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"content": json.dumps({"response": "Would you like to speak to a member of staff?", "source_ids": [], "uncertain": True, "escalate": True, "intent": {"intent": "unclear", "confidence": 1, "proposed_action": "clarify"}})}})
    monkeypatch.setattr(conversation.httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(model)))
    await jobs.submit("test", "", actor, pipeline=True)
    await jobs.sweep()
    result = (await jobs.list("test", actor))["items"][0]
    assert calls == ["stt", "inference", "tts"] and result["status"] == "passed"
    assert not result["evidence"]["live_telephony_verified"] and result["evidence"]["escalation_required"]
    assert "Would you like to speak" not in str(result)


async def test_global_worker_lease_prevents_concurrent_execution(speech_context, mock_db):
    jobs, _, actor, _ = speech_context
    await jobs.submit("test", "test-stt", actor)
    await mock_db.voice_runtime_leases.insert_one({"_id": "speech-test", "token": "other-worker", "until": utc_now() + timedelta(minutes=1)})
    assert await jobs.sweep() == 0
    assert (await jobs.list("test", actor))["items"][0]["status"] == "queued"


async def test_queue_bound_is_enforced(speech_context):
    from app.core.exceptions import ConflictError
    jobs, _, actor, _ = speech_context
    for index in range(10):
        try:
            await jobs.submit("test", "test-stt", actor)
        except ConflictError:
            pytest.fail(f"Queue rejected admission after {index} jobs")
    with pytest.raises(ConflictError):
        await jobs.submit("test", "test-stt", actor)


async def test_speech_evidence_expires_and_configuration_changes_invalidate_it(speech_context, mock_db, monkeypatch):
    jobs, _, actor, cfg = speech_context
    async def fake_execute(command, directory, timeout, memory):
        (directory / "result.txt").write_text("This is a reference test.")
    monkeypatch.setattr(speech_runtime, "execute", fake_execute)
    await jobs.submit("test", "test-stt", actor)
    await jobs.sweep()
    assert (await jobs.summary("test"))["stt"] == "functional_test_passed"
    await mock_db.voice_speech_jobs.update_one({}, {"$set": {"finished_at": utc_now() - timedelta(minutes=16)}})
    assert (await jobs.summary("test"))["stt"] != "functional_test_passed"
    await mock_db.voice_speech_jobs.update_one({}, {"$set": {"finished_at": utc_now()}})
    cfg.profiles["test-stt"].version = "changed-profile-version"
    assert (await jobs.summary("test"))["stt"] != "functional_test_passed"


async def test_pipeline_rejects_unapproved_citations_before_tts(monkeypatch, speech_config):
    from app.features.voice_assistant.local_pipeline import LocalUtterancePipeline
    from app.features.voice_assistant.conversation import LocalConversationAdapter
    async def recognize(self, profile, audio):
        return "Synthetic test question"
    async def answer(self, **kwargs):
        return {"response": "Unapproved answer", "source_ids": ["forged-source"]}
    async def no_speech(self, profile, text):
        pytest.fail("Unapproved citation must prevent synthesis")
    monkeypatch.setattr(LocalSpeechRuntime, "transcribe", recognize)
    monkeypatch.setattr(LocalSpeechRuntime, "synthesize", no_speech)
    monkeypatch.setattr(LocalConversationAdapter, "respond", answer)
    with pytest.raises(ValueError, match="unapproved"):
        await LocalUtterancePipeline(LocalSpeechRuntime(speech_config), LocalConversationAdapter()).respond(audio=sample_wav(), stt_profile="test-stt", tts_profile="not-used", sources=[], instructions="Synthetic test only", operational_rules="No tools", language="en")


@pytest.mark.skipif(sys.platform != "linux", reason="Actual POSIX resource limits require the Linux deployment/CI runner.")
async def test_real_posix_child_deadline_and_cleanup(tmp_path):
    import os
    pid_file = tmp_path / "child.pid"
    command = [sys.executable, "-c", "import os,time; from pathlib import Path; Path('child.pid').write_text(str(os.getpid())); time.sleep(20)"]
    with pytest.raises(TimeoutError):
        await speech_runtime.execute(command, tmp_path, 5, 256)
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
