import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/shared/api/errors";
import { emergencyVoiceStop, getPlatform, getSpeechJobs, getSpeechProfiles, getSpeechTestAudio, setActivation, startPipelineTest, startSpeechTest, updateComponent, type PlatformState, type VoiceComponent, type VoiceEnvironment } from "./platformApi";

const labels: Record<VoiceComponent, string> = { telephony: "Native PBX", stt: "Speech recognition", tts: "Speech synthesis", inference: "Local AI inference", media: "Voice media", workers: "Voice verification workers", recording: "Recording", transfer: "Human transfer", smartflo: "Optional Smartflo" };

export function PlatformControlsPanel() {
  const { userId, role } = useAuth(); const owner = role === "owner";
  const client = useQueryClient();
  const [environment, setEnvironment] = useState<VoiceEnvironment>("test");
  const [reason, setReason] = useState(""); const [error, setError] = useState<string | null>(null);
  const [working, setBusy] = useState(false); const [stopping, setStopping] = useState(false);
  const busy = working || stopping; const [audio, setAudio] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const state = useQuery({ queryKey: ["voice", userId, "platform", environment], queryFn: () => getPlatform(environment), enabled: owner, refetchInterval: 10000 });
  const profiles = useQuery({ queryKey: ["voice", userId, "speech-profiles"], queryFn: getSpeechProfiles, enabled: owner });
  const jobs = useQuery({ queryKey: ["voice", userId, "speech-jobs", environment, page], queryFn: () => getSpeechJobs(environment, page), enabled: owner, refetchInterval: 5000 });
  useEffect(() => () => { if (audio) URL.revokeObjectURL(audio); }, [audio]);
  useEffect(() => { setAudio(null); }, [environment, userId]);
  async function action(work: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await work(); await client.invalidateQueries({ queryKey: ["voice", userId] }); }
    catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
  }
  async function emergency() {
    setStopping(true); setError(null);
    try { await emergencyVoiceStop(environment, reason.trim().length >= 5 ? reason : "Owner emergency disable"); await client.invalidateQueries({ queryKey: ["voice", userId] }); }
    catch (err) { setError(getErrorMessage(err)); } finally { setStopping(false); }
  }
  if (!owner) return <p>Platform controls are restricted to the Owner.</p>;
  const data = state.data;
  const reasonValid = reason.trim().length >= 5;
  return <section aria-labelledby="platform-controls-title" className="space-y-5 mb-6">
    <h2 id="platform-controls-title" className="text-xl font-semibold">Self-hosted platform controls</h2>
    <p>Enablement permits local testing only. Installation, successful verification and production activation are separate steps. Live PBX media and speech acceptance remain blocked.</p>
    <SelectField label="Voice environment" value={environment} disabled={busy} onChange={e => { setEnvironment(e.target.value as VoiceEnvironment); setPage(1); }} options={[{ value: "test", label: "Test — no real calls" }, { value: "production", label: "Production — activation blocked" }]} />
    <ErrorBanner message={error ?? (state.error ? getErrorMessage(state.error) : profiles.error ? getErrorMessage(profiles.error) : jobs.error ? getErrorMessage(jobs.error) : null)} />
    <FormField label="Change reason (no credentials or customer details)" minLength={5} maxLength={160} value={reason} onChange={e => setReason(e.target.value)} />
    <Button variant="danger" loading={stopping} onClick={() => void emergency()}>Emergency disable {environment} voice</Button>
    <p className="text-sm">Immediately blocks new AI handling and call directions in this environment. No live calls exist in this implementation; active-call draining is not verified.</p>
    {state.isPending && <p role="status">Loading platform controls…</p>}
    {!data && state.error && <Button onClick={() => void state.refetch()}>Retry platform status</Button>}
    {data && <>
      <p role="status">Inbound: {data.inbound ? "Enabled" : "Disabled"} · Outbound: {data.outbound ? "Enabled" : "Disabled"} · Processing: {data.processing ? "Enabled" : "Disabled"} · Emergency stop: {data.emergency_stopped ? "Set" : "Clear"}</p>
      <div className="grid gap-4 lg:grid-cols-2">{(Object.keys(labels) as VoiceComponent[]).map(key => {
        const current = data.components[key];
        const options = profiles.data?.profiles.filter(profile => profile.kind === key) ?? [];
        return <section key={key} className="border rounded-xl bg-card p-4 space-y-3" aria-label={labels[key]}>
          <h3 className="font-semibold">{labels[key]}</h3>
          <p>{!current.testing_supported ? "Runtime not implemented — enablement blocked" : current.enabled ? "Enabled for testing; runtime unverified" : "Disabled"}</p>
          {(key === "stt" || key === "tts") && <SelectField label={`${labels[key]} profile`} value={current.profile_id ?? ""} disabled={busy || !reasonValid} onChange={e => void action(() => updateComponent(environment, key, data.version, false, e.target.value || null, reason))} options={[{ value: "", label: "No approved model configured" }, ...options.map(profile => ({ value: profile.id, label: `${profile.engine} · ${profile.language} · ${profile.version}` }))]} />}
          <Button variant="secondary" disabled={busy || !reasonValid || (!current.enabled && !current.testing_supported)} onClick={() => void action(() => updateComponent(environment, key, data.version, !current.enabled, current.profile_id, reason))}>{current.enabled ? "Disable" : "Enable for testing"} {labels[key]}</Button>
          {(key === "stt" || key === "tts") && <Button disabled={busy || !current.enabled || !current.profile_id || !data.components.workers.enabled} onClick={() => void action(() => startSpeechTest(environment, current.profile_id!))}>Run actual local {key.toUpperCase()} test</Button>}
        </section>;
      })}</div>
      <p>{profiles.data?.message}</p>
      <p className="text-sm">Install pinned engines and approved models through the deployment procedure. No downloads run at startup or from these switches. Configure native credentials in <Link className="text-primary underline" to="/voice-assistant/providers">Provider Connections</Link>.</p>
      <h3 className="font-semibold">Backend activation checklist</h3>
      <Button disabled={busy || !data.components.stt.enabled || !data.components.tts.enabled || !data.components.inference.enabled || !data.components.workers.enabled} onClick={() => void action(() => startPipelineTest(environment))}>Test local STT → AI → TTS audio</Button>
      <p className="text-sm">Uses the approved reference audio only. Per-utterance model loading; not a real-time PBX or live-call test.</p>
      <ul className="space-y-2">{data.gates.map(gate => <li key={gate.key}><strong>{gate.passed ? "Passed" : "Blocked"}: {gate.key.replaceAll("_", " ")}</strong> — {gate.remediation}</li>)}</ul>
      {(["inbound", "outbound", "processing"] as const).map(direction => <div className="flex flex-wrap gap-2 items-center" key={direction}>
        <Button disabled title="Verified live runtime and all backend gates required">Enable live {direction} (blocked)</Button>
        <Button variant="secondary" disabled={busy || !reasonValid} onClick={() => void action(() => setActivation(environment, { version: data.version, direction, enabled: false, reason }))}>Disable {direction}</Button>
      </div>)}
      <History data={data} />
    </>}
    <h3 className="font-semibold">Local speech verification jobs</h3>
    <p className="text-sm">One verification at a time through the existing ARQ worker. Results and encrypted sample audio expire after one hour. No customer recording is used.</p>
    {jobs.data?.items.length === 0 && <p>No local speech tests requested.</p>}
    {jobs.data?.items.map(job => <article className="border rounded-xl p-4 space-y-2" key={job.id}><p>{job.profile_id} · {job.status} · {job.latency_ms == null ? "Latency unavailable" : `${job.latency_ms} ms`}</p><p>{job.diagnostic}</p>{job.evidence && <p>Evidence: {Object.entries(job.evidence).map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`).join(" · ")}</p>}{["tts", "pipeline"].includes(job.kind) && job.status === "passed" && <Button variant="secondary" onClick={() => void action(async () => { const blob = await getSpeechTestAudio(environment, job.id); setAudio(URL.createObjectURL(blob)); })}>Load test audio</Button>}</article>)}
    {audio && <audio controls src={audio} aria-label="Generated local speech verification audio" />}
    <div className="flex gap-2"><Button variant="secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous tests</Button><Button variant="secondary" disabled={page * 25 >= (jobs.data?.total ?? 0)} onClick={() => setPage(page + 1)}>Next tests</Button></div>
  </section>;
}

function History({ data }: { data: PlatformState }) {
  return <details><summary>Control audit history ({data.history.length} recent entries)</summary><ul>{[...data.history].reverse().map((entry, index) => <li className="py-2" key={`${entry.at}:${index}`}>{new Date(entry.at).toLocaleString()} · {entry.event} · {entry.actor_id} · {entry.reason}</li>)}</ul></details>;
}
