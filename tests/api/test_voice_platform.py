import asyncio
import io
import wave
from datetime import timedelta
from uuid import uuid4
from zipfile import ZipFile

import pytest
from bson import ObjectId

from app.core.exceptions import ForbiddenError, ValidationError
from app.features.auth.models import User
from app.features.voice_assistant.catalog import initialize_voice_module
from app.features.voice_assistant.knowledge_import import extract_document
from app.features.voice_assistant.media_contracts import BoundedAudioBuffer, ComposedSpeechAdapter
from app.features.voice_assistant.models import CallSession
from app.features.voice_assistant.recording_service import RecordingService
from app.features.voice_assistant.recording_storage import (
    PrivateRecordingStorage,
    RecordingConfig,
    validate_wav,
)
from app.features.voice_assistant.service import VoiceService
from app.utils.datetime import utc_now

BASE = "/api/v1/voice-assistant"
pytestmark = pytest.mark.usefixtures("platform_setup")


@pytest.fixture
async def platform_setup(mock_db, monkeypatch, tmp_path):
    from app.features.voice_assistant import recording_storage

    config = RecordingConfig(recordings_dir=str(tmp_path / "voice-recordings"))
    monkeypatch.setattr(recording_storage, "get_recording_config", lambda: config)
    await initialize_voice_module(mock_db)
    return PrivateRecordingStorage(config)


def wav_bytes(seconds=1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * int(8000 * seconds))
    return buffer.getvalue()


def zipped(files):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


async def ended_call(mock_db, owner_id=None):
    if owner_id is None:
        user = await mock_db.users.find_one({"role": "owner"})
        owner_id = str(user["_id"])
    call = CallSession(
        direction="incoming",
        contact_label="Test-only imported artifact",
        status="completed",
        idempotency_key=uuid4().hex,
        owner_user_id=owner_id,
        deadline_at=utc_now(),
        ended_at=utc_now(),
    ).model_dump(by_alias=True, exclude={"id"})
    result = await mock_db.voice_calls.insert_one(call)
    return str(result.inserted_id)


async def import_audio(client, headers, call_id, *, key=None, audio=None):
    return await client.post(
        f"{BASE}/recordings/import",
        headers=headers,
        files={
            "file": ("actual-test.wav", audio if audio is not None else wav_bytes(), "audio/wav")
        },
        data={
            "call_id": call_id,
            "idempotency_key": key or uuid4().hex,
            "consent_reference": "test-only-policy-evidence",
            "retention_days": "1",
        },
    )


async def article_action(client, headers, article, action, target=None):
    return await client.post(
        f"{BASE}/knowledge/{article['id']}/actions",
        headers=headers,
        json={
            "action": action,
            "version": article["version"],
            **({"target_version": target} if target else {}),
        },
    )


async def import_article(client, headers):
    response = await client.post(
        f"{BASE}/knowledge/import",
        headers=headers,
        files={
            "file": (
                "policy.txt",
                b"EMI reconciliation requires an authorized review and verified payment evidence.",
                "text/plain",
            )
        },
        data={"title": "EMI evidence policy", "language": "en"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def evaluate(client, headers, article, facts=None, negative=False):
    return await client.post(
        f"{BASE}/knowledge/{article['id']}/evaluations",
        headers=headers,
        json={
            "version": article["version"],
            "cases": [
                {
                    "question": "Unrelated weather" if negative else "EMI reconciliation evidence?",
                    "required_facts": []
                    if negative
                    else (facts or ["authorized review", "verified payment evidence"]),
                    "expect_evidence": not negative,
                }
            ],
        },
    )


async def test_document_draft_evaluate_publish_edit_and_approved_rollback(
    client, owner_headers, mock_db
):
    article = await import_article(client, owner_headers)
    assert article["status"] == "draft" and article["source"]["scan_status"] == "not_scanned"
    assert not await VoiceService(mock_db).retrieve("EMI reconciliation", "en")
    review = (await article_action(client, owner_headers, article, "review")).json()["data"]
    assert (await article_action(client, owner_headers, review, "publish")).status_code == 409
    failed = await evaluate(client, owner_headers, review, ["payment is guaranteed"])
    assert not failed.json()["data"]["passed"]
    negative = await evaluate(client, owner_headers, review, negative=True)
    assert negative.json()["data"]["passed"] and not negative.json()["data"]["release_eligible"]
    assert (await article_action(client, owner_headers, review, "publish")).status_code == 409
    report = (await evaluate(client, owner_headers, review)).json()["data"]
    assert report["passed"] and report["semantic_groundedness"] == "not_evaluated"
    first = (await article_action(client, owner_headers, review, "publish")).json()["data"]
    assert first["publication"]["version"] == first["version"]
    edit = await client.put(
        f"{BASE}/knowledge/{article['id']}",
        headers=owner_headers,
        json={
            "title": article["title"],
            "content": "EMI reconciliation now requires a supervisor investigation before a status update.",
            "language": "en",
            "version": first["version"],
        },
    )
    draft = edit.json()["data"]
    sources = await VoiceService(mock_db).retrieve("EMI reconciliation", "en")
    assert sources[0]["version"] == first["version"] and "verified payment" in sources[0]["excerpt"]
    stale = await evaluate(client, owner_headers, first)
    assert stale.status_code == 409
    review = (await article_action(client, owner_headers, draft, "review")).json()["data"]
    # Old passed evaluation cannot release changed contents.
    assert (await article_action(client, owner_headers, review, "publish")).status_code == 409
    assert (await evaluate(client, owner_headers, review, ["supervisor investigation"])).json()[
        "data"
    ]["passed"]
    second = (await article_action(client, owner_headers, review, "publish")).json()["data"]
    assert len(second["publications"]) == 2
    restored = await article_action(
        client, owner_headers, second, "rollback_published", first["version"]
    )
    assert restored.status_code == 200, restored.text
    assert (await VoiceService(mock_db).retrieve("EMI reconciliation", "en"))[0][
        "version"
    ] == first["version"]
    archived = (
        await article_action(client, owner_headers, restored.json()["data"], "archive")
    ).json()["data"]
    assert archived["publication"] is None and not await VoiceService(mock_db).retrieve(
        "EMI reconciliation", "en"
    )
    assert (
        await mock_db.audit_logs.count_documents(
            {"event_type": "voice_assistant.knowledge_rollback_published"}
        )
        == 1
    )


async def test_document_import_limits_and_permissions(
    client, owner_headers, employee_headers, mock_db
):
    assert (
        await client.post(
            f"{BASE}/knowledge/import",
            headers=employee_headers,
            files={"file": ("a.txt", b"Reviewed documents only. No account facts.", "text/plain")},
            data={"title": "Policy"},
        )
    ).status_code == 403
    assert (
        await client.post(
            f"{BASE}/knowledge/import",
            headers=owner_headers,
            files={"file": ("a.pdf", b"%PDF-unsafe", "application/pdf")},
            data={"title": "Policy"},
        )
    ).status_code == 422
    article = await import_article(client, owner_headers)
    assert (await import_article_response(client, owner_headers)).status_code == 409
    assert (
        await client.post(
            f"{BASE}/knowledge/{article['id']}/evaluations",
            headers=owner_headers,
            json={
                "version": article["version"],
                "cases": [{"question": "EMI?", "required_facts": []}],
            },
        )
    ).status_code == 422
    assert await mock_db.voice_knowledge.count_documents({}) == 1


async def import_article_response(client, headers):
    return await client.post(
        f"{BASE}/knowledge/import",
        headers=headers,
        files={
            "file": (
                "policy.txt",
                b"EMI reconciliation requires an authorized review and verified payment evidence.",
                "text/plain",
            )
        },
        data={"title": "Duplicate content", "language": "en"},
    )


@pytest.mark.parametrize(
    "filename,content,mime",
    [
        ("x.txt", b"\x00binary\x00", "text/plain"),
        ("x.csv", b"Policy,Terms\n=RUN(),Ignore safety", "text/csv"),
        ("x.xlsm", b"macro", "application/octet-stream"),
        ("x.docx", b"not zipped", "application/octet-stream"),
        ("x.txt", b"a" * 50001, "text/plain"),
        ("x.txt", b"valid content but wrong media type", "text/html"),
    ],
    ids=["binary-text", "formula-csv", "macro", "invalid-zip", "oversized-text", "wrong-mime"],
)
def test_unsafe_knowledge_files_rejected(filename, content, mime):
    with pytest.raises(ValidationError):
        extract_document(content, filename, mime)


def test_safe_docx_utf16_xlsx_and_external_relationship_rejection():
    docx = zipped(
        {
            "word/document.xml": '<w:document xmlns:w="urn:w"><w:p><w:r><w:t>Reviewed EMI reconciliation policy text.</w:t></w:r></w:p></w:document>'
        }
    )
    assert "Reviewed EMI" in extract_document(docx, "policy.docx", None)
    assert "Reviewed EMI" in extract_document(
        "Reviewed EMI policy text in UTF16.".encode("utf-16"), "policy.txt", None
    )
    bad = zipped(
        {"word/document.xml": '<!DOCTYPE document [<!ENTITY x "unsafe">]><document>&x;</document>'}
    )
    with pytest.raises(ValidationError):
        extract_document(bad, "policy.docx", None)
    external = zipped(
        {
            "word/document.xml": "<document/>",
            "_rels/.rels": '<Relationships><Relationship TargetMode="External" Target="https://untrusted.test"/></Relationships>',
        }
    )
    with pytest.raises(ValidationError):
        extract_document(external, "policy.docx", None)
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.active.append(["Reviewed policy", "EMI reconciliation requires authorized review"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    assert "authorized review" in extract_document(buffer.getvalue(), "policy.xlsx", None)
    formula = zipped(
        {
            "xl/worksheets/sheet1.xml": '<worksheet xmlns="urn:x"><sheetData><row r="1"><c r="A1"><f>SUM(A1:A2)</f><v>1</v></c></row></sheetData></worksheet>'
        }
    )
    with pytest.raises(ValidationError):
        extract_document(formula, "policy.xlsx", None)
    sparse = zipped(
        {
            "xl/worksheets/sheet1.xml": '<worksheet xmlns="urn:x"><sheetData><row r="1"><c r="XFD1048576"><v>1</v></c></row></sheetData></worksheet>'
        }
    )
    with pytest.raises(ValidationError):
        extract_document(sparse, "policy.xlsx", None)


async def test_real_artifact_encrypted_playback_range_transcript_delete(
    client, owner_headers, mock_db, platform_setup
):
    call_id = await ended_call(mock_db)
    data, key = wav_bytes(), uuid4().hex
    response = await import_audio(client, owner_headers, call_id, key=key, audio=data)
    assert response.status_code == 200, response.text
    record = response.json()["data"]
    assert record["status"] == "completed" and record["origin"] == "imported_artifact"
    assert platform_setup.path(record["id"]).read_bytes() != data
    assert "RIFF" not in platform_setup.path(record["id"]).read_text()
    duplicate = await import_audio(client, owner_headers, call_id, key=key, audio=data)
    assert duplicate.json()["data"]["id"] == record["id"]
    assert (
        await import_audio(client, owner_headers, call_id, key=key, audio=wav_bytes(2))
    ).status_code == 409
    audio_url = f"{BASE}/recordings/{record['id']}/audio"
    full = await client.get(audio_url, headers=owner_headers)
    assert (
        full.status_code == 200
        and full.content == data
        and "no-store" in full.headers["cache-control"]
    )
    part = await client.get(audio_url, headers={**owner_headers, "Range": "bytes=0-43"})
    assert part.status_code == 206 and part.content == data[:44]
    for byte_range in ("bytes=900000-", "bytes=0-1,4-5", "bytes=-0", "bytes=" + "1" * 500):
        assert (
            await client.get(audio_url, headers={**owner_headers, "Range": byte_range})
        ).status_code == 416
    transcript = {
        "version": record["version"],
        "recognizer_label": "Test fixture recognizer",
        "language": "en",
        "segments": [
            {
                "speaker": "caller",
                "start_seconds": 0,
                "end_seconds": 0.8,
                "text": "My EMI was paid yesterday.",
                "confidence": 0.8,
            }
        ],
    }
    saved = await client.put(
        f"{BASE}/recordings/{record['id']}/transcript", headers=owner_headers, json=transcript
    )
    assert saved.status_code == 200, saved.text
    listed = (await client.get(f"{BASE}/recordings", headers=owner_headers)).json()["data"]
    assert "transcript_ciphertext" not in str(listed) and "My EMI" not in str(listed)
    stored = await mock_db.voice_recordings.find_one({"_id": ObjectId(record["id"])})
    assert "My EMI" not in stored["transcript_ciphertext"]
    recognized = (
        await client.get(f"{BASE}/recordings/{record['id']}/transcript", headers=owner_headers)
    ).json()["data"]
    assert recognized["segments"][0]["text"] == transcript["segments"][0]["text"]
    assert (
        recognized["summary"] is None and "not_independently_verified" in recognized["provenance"]
    )
    stale = await client.delete(
        f"{BASE}/recordings/{record['id']}?version={record['version']}", headers=owner_headers
    )
    assert stale.status_code == 409
    deleted = await client.delete(
        f"{BASE}/recordings/{record['id']}?version={saved.json()['data']['version']}",
        headers=owner_headers,
    )
    assert deleted.status_code == 200 and not platform_setup.path(record["id"]).exists()
    assert (await client.get(audio_url, headers=owner_headers)).status_code == 403
    tombstone = await mock_db.voice_recordings.find_one({"_id": ObjectId(record["id"])})
    assert tombstone["status"] == "deleted" and "transcript_ciphertext" not in tombstone
    assert (
        await mock_db.audit_logs.count_documents(
            {"event_type": "voice_assistant.recording_playback"}
        )
        >= 1
    )


async def test_recording_expiry_immediate_and_worker_deletion(
    client, owner_headers, mock_db, platform_setup
):
    record = (await import_audio(client, owner_headers, await ended_call(mock_db))).json()["data"]
    await mock_db.voice_recordings.update_one(
        {"_id": ObjectId(record["id"])}, {"$set": {"expires_at": utc_now() - timedelta(seconds=1)}}
    )
    assert (
        await client.get(f"{BASE}/recordings/{record['id']}/audio", headers=owner_headers)
    ).status_code == 403
    listing = (await client.get(f"{BASE}/recordings", headers=owner_headers)).json()["data"]
    assert listing["items"][0]["status"] == "expired"
    service = RecordingService(mock_db, platform_setup)
    assert (await service.reconcile())["processed"] == 1
    assert (await service.reconcile())["processed"] == 0
    assert not platform_setup.path(record["id"]).exists()


async def test_storage_corruption_missing_and_recovery(
    client, owner_headers, mock_db, platform_setup
):
    record = (await import_audio(client, owner_headers, await ended_call(mock_db))).json()["data"]
    path = platform_setup.path(record["id"])
    original = path.read_bytes()
    path.write_bytes(b"corrupted ciphertext")
    assert (
        await client.get(f"{BASE}/recordings/{record['id']}/audio", headers=owner_headers)
    ).status_code == 422
    path.write_bytes(original)
    await mock_db.voice_recordings.update_one(
        {"_id": ObjectId(record["id"])},
        {"$set": {"status": "pending", "lease_until": utc_now() - timedelta(seconds=1)}},
    )
    assert (await RecordingService(mock_db, platform_setup).reconcile())["processed"] == 1
    doc = await mock_db.voice_recordings.find_one({"_id": ObjectId(record["id"])})
    assert doc["status"] == "completed" and doc["recovered_at"]
    path.unlink()
    await mock_db.voice_recordings.update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": "pending", "lease_until": utc_now() - timedelta(seconds=1)}},
    )
    assert (await RecordingService(mock_db, platform_setup).reconcile())["processed"] == 1
    doc = await mock_db.voice_recordings.find_one({"_id": doc["_id"]})
    assert doc["status"] == "failed"
    assert (
        await client.post(
            f"{BASE}/recordings/{record['id']}/recover?version={doc['version']}",
            headers=owner_headers,
        )
    ).status_code == 422


async def test_storage_write_failure_never_marks_completed(
    client, owner_headers, mock_db, monkeypatch
):
    def fail(*_args):
        raise OSError("test-only disk failure")

    monkeypatch.setattr(PrivateRecordingStorage, "put", fail)
    response = await import_audio(client, owner_headers, await ended_call(mock_db))
    assert response.status_code == 422 and "disk failure" not in response.text
    assert await mock_db.voice_recordings.count_documents({"status": "completed"}) == 0
    assert await mock_db.voice_recordings.count_documents({"status": "failed"}) == 1


async def test_recording_scope_permissions_and_transcript_bounds(
    client, owner_headers, employee_headers, mock_db, platform_setup
):
    assert (await client.get(f"{BASE}/recordings", headers=employee_headers)).status_code == 403
    assert (await client.get(f"{BASE}/recordings")).status_code in (401, 403)
    record = (await import_audio(client, owner_headers, await ended_call(mock_db))).json()["data"]
    actor = User(_id=str(ObjectId()), mobile="9000000098", role="employee")
    service = RecordingService(mock_db, platform_setup)
    assert (await service.list(actor, page=1, status=None, call_id=None))["total"] == 0
    with pytest.raises(ForbiddenError):
        await service.audio(record["id"], actor, download=False)
    for segments in (
        [
            {
                "speaker": "caller",
                "start_seconds": 0,
                "end_seconds": 2,
                "text": "Outside audio duration",
            }
        ],
        [{"speaker": "caller", "start_seconds": 0.8, "end_seconds": 0.4, "text": "Invalid time"}],
    ):
        assert (
            await client.put(
                f"{BASE}/recordings/{record['id']}/transcript",
                headers=owner_headers,
                json={
                    "version": record["version"],
                    "language": "en",
                    "recognizer_label": "Test recognizer",
                    "segments": segments,
                },
            )
        ).status_code == 422
    assert (await import_audio(client, employee_headers, record["call_id"])).status_code == 403
    assert (
        await import_audio(client, owner_headers, record["call_id"], audio=b"not a WAV")
    ).status_code == 422


def test_wav_and_private_path_limits(platform_setup):
    with pytest.raises(ValidationError):
        validate_wav(wav_bytes()[:-20])
    for root in ("relative-path", "/", "C:/public/recordings"):
        with pytest.raises(ValueError):
            RecordingConfig(recordings_dir=root)
    with pytest.raises(ValidationError):
        platform_setup.path("../../escape")


async def test_bounded_audio_backpressure_and_close():
    buffer = BoundedAudioBuffer(max_frames=1, max_frame_bytes=160, timeout_seconds=0.01)
    await buffer.feed(b"x" * 160)
    with pytest.raises(TimeoutError):
        await buffer.feed(b"y" * 160)
    assert buffer.closed and buffer.queue.qsize() <= 1
    with pytest.raises(StopAsyncIteration):
        await anext(buffer)
    empty = BoundedAudioBuffer()
    waiting = asyncio.create_task(anext(empty))
    await asyncio.sleep(0)
    empty.close()
    with pytest.raises(StopAsyncIteration):
        await waiting


async def test_independent_recognition_and_synthesis_adapters():
    class Recognition:
        async def recognize(self, audio, language):
            async for _frame in audio:
                yield "test-only recognition fixture"

    class Synthesis:
        async def synthesize(self, text, language):
            yield text.encode()

    async def audio():
        yield b"audio fixture"

    composed = ComposedSpeechAdapter(Recognition(), Synthesis())
    assert [text async for text in composed.recognize(audio(), "en")] == [
        "test-only recognition fixture"
    ]
    assert [frame async for frame in composed.synthesize("fixture", "en")] == [b"fixture"]


async def test_upload_envelope_limits_before_spooling(client, owner_headers, mock_db):
    for endpoint in ("knowledge/import", "recordings/import"):
        response = await client.post(
            f"{BASE}/{endpoint}",
            headers={**owner_headers, "Content-Length": str(30 * 1024 * 1024)},
            content=b"x",
        )
        assert (
            response.status_code == 413
            and response.json()["error"]["code"] == "voice_upload_rejected"
        )

    async def streamed_body():
        yield b"x" * (6 * 1024 * 1024)

    response = await client.post(
        f"{BASE}/knowledge/import",
        headers={**owner_headers, "Content-Type": "multipart/form-data; boundary=test"},
        content=streamed_body(),
    )
    assert (
        response.status_code == 413 and response.json()["error"]["code"] == "voice_upload_rejected"
    )
    assert await mock_db.voice_knowledge.count_documents({}) == 0


async def test_retention_failure_is_retried_and_dates_filter_real_records(
    client, owner_headers, mock_db, platform_setup, monkeypatch
):
    record = (await import_audio(client, owner_headers, await ended_call(mock_db))).json()["data"]
    today = utc_now()
    response = await client.get(
        f"{BASE}/recordings",
        headers=owner_headers,
        params={
            "since": (today - timedelta(days=1)).isoformat(),
            "until": (today + timedelta(days=1)).isoformat(),
        },
    )
    assert response.json()["data"]["total"] == 1
    assert (
        await client.get(f"{BASE}/recordings?since=2026-01-01T00:00:00", headers=owner_headers)
    ).status_code == 422
    await mock_db.voice_recordings.update_one(
        {"_id": ObjectId(record["id"])}, {"$set": {"expires_at": today - timedelta(seconds=1)}}
    )
    assert (await client.get(f"{BASE}/recordings?status=completed", headers=owner_headers)).json()[
        "data"
    ]["total"] == 0
    assert (await client.get(f"{BASE}/recordings?status=expired", headers=owner_headers)).json()[
        "data"
    ]["total"] == 1
    original_delete = platform_setup.delete

    def fail(*_args):
        raise OSError("test-only deletion failure")

    monkeypatch.setattr(platform_setup, "delete", fail)
    service = RecordingService(mock_db, platform_setup)
    assert (await service.reconcile())["failed"] == 1
    doc = await mock_db.voice_recordings.find_one({"_id": ObjectId(record["id"])})
    assert doc["status"] == "deletion_pending" and platform_setup.path(record["id"]).exists()
    monkeypatch.setattr(platform_setup, "delete", original_delete)
    assert (await service.reconcile())["processed"] == 1
    assert not platform_setup.path(record["id"]).exists()


async def test_recording_view_grant_does_not_imply_download(
    client, owner_headers, employee_headers, mock_db, master_data
):
    from app.features.access_control.models import EmployeeRole, Role, RolePermission
    from app.features.employee.models import Employee

    user = await mock_db.users.find_one({"mobile": "9000000002"})
    employee = Employee(
        user_id=str(user["_id"]),
        employee_code="VOICE-RECORDING-TEST",
        first_name="Test",
        last_name="Viewer",
        display_name="Test Viewer",
        mobile=user["mobile"],
        email="recording-viewer@example.test",
        joining_date=utc_now(),
        employment_type="full_time",
        **master_data,
    )
    employee_id = (
        await mock_db.employees.insert_one(employee.model_dump(by_alias=True, exclude={"id"}))
    ).inserted_id
    role_id = (
        await mock_db.roles.insert_one(
            Role(name="Recording Viewer").model_dump(by_alias=True, exclude={"id"})
        )
    ).inserted_id
    permission = await mock_db.permissions.find_one(
        {"module": "voice_assistant", "resource": "recordings"}
    )
    grant_id = (
        await mock_db.role_permissions.insert_one(
            RolePermission(
                role_id=str(role_id), permission_id=str(permission["_id"]), granted_actions=["view"]
            ).model_dump(by_alias=True, exclude={"id"})
        )
    ).inserted_id
    await mock_db.employee_roles.insert_one(
        EmployeeRole(employee_id=str(employee_id), role_id=str(role_id)).model_dump(
            by_alias=True, exclude={"id"}
        )
    )
    own = (
        await import_audio(client, owner_headers, await ended_call(mock_db, str(user["_id"])))
    ).json()["data"]
    other = (await import_audio(client, owner_headers, await ended_call(mock_db))).json()["data"]
    listing = (await client.get(f"{BASE}/recordings", headers=employee_headers)).json()["data"]
    assert listing["total"] == 1 and listing["items"][0]["id"] == own["id"]
    assert (
        await client.get(f"{BASE}/recordings/{own['id']}/audio", headers=employee_headers)
    ).status_code == 200
    assert (
        await client.get(f"{BASE}/recordings/{other['id']}/audio", headers=employee_headers)
    ).status_code == 403
    assert (
        await client.get(
            f"{BASE}/recordings/{own['id']}/audio?download=true", headers=employee_headers
        )
    ).status_code == 403
    await mock_db.role_permissions.update_one(
        {"_id": grant_id}, {"$set": {"granted_actions": ["view", "download"]}}
    )
    assert (
        await client.get(
            f"{BASE}/recordings/{own['id']}/audio?download=true", headers=employee_headers
        )
    ).status_code == 200


async def test_catalog_permissions_preserve_admin_choices_and_no_implicit_grants(mock_db):
    await mock_db.permissions.update_one(
        {"module": "voice_assistant", "resource": "recordings"},
        {"$set": {"label": "Admin recording label"}},
    )
    await initialize_voice_module(mock_db)
    assert (
        await mock_db.permissions.find_one({"module": "voice_assistant", "resource": "recordings"})
    )["label"] == "Admin recording label"
    assert (
        await mock_db.permissions.count_documents(
            {"module": "voice_assistant", "resource": "recordings"}
        )
        == 1
    )
    assert await mock_db.role_permissions.count_documents({}) == 0


async def test_dynamic_core_uses_negotiated_pcm_without_smartflo_transport():
    from app.features.voice_assistant.dynamic_audio import DynamicAudioConversation
    from app.features.voice_assistant.media_contracts import AudioFormat

    class Codec:
        stopped = False
        audio_format = AudioFormat(encoding="pcm_s16le", sample_rate=16000)

        def output(self, *, audio=None, mark=None, clear=False):
            return {"audio": audio, "mark": mark, "clear": clear}

    class Model:
        async def respond(self, **_kwargs):
            return {
                "response": "Test dynamic response",
                "source_ids": ["approved"],
                "uncertain": False,
            }

    class Speech:
        async def recognize(self, audio, language):
            async for _frame in audio:
                yield "Test fixture"

        async def synthesize(self, text, language):
            yield b"\x01\x00" * 4

    async def retrieve(question, language):
        return [{"id": "approved", "excerpt": "Approved evidence for isolated test."}]

    sent = []

    async def send(message):
        sent.append(message)

    engine = DynamicAudioConversation(
        model=Model(),
        speech=Speech(),
        codec=Codec(),
        retrieve=retrieve,
        send=send,
        instructions="Test behavior",
        operational_rules="Test policy",
    )
    await engine.question("A changing natural question")
    await engine.drain()
    frames = [event["audio"] for event in sent if event["audio"] is not None]
    assert len(frames) == 1 and len(frames[0]) == 640
    assert frames[0][:8] == b"\x01\x00" * 4 and frames[0][8:] == b"\0" * 632
    await engine.close()
