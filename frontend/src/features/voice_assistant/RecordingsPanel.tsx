import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { usePermissions } from "@/features/access_control/usePermissions";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/shared/api/errors";
import { deleteRecording, getRecordingAudio, getRecordings, getTranscript, importRecording, recoverRecording, saveTranscript, type Recording, type Transcript } from "./api";

export function RecordingsPanel() {
  const { userId } = useAuth(); const { can } = usePermissions(); const client = useQueryClient();
  const [page, setPage] = useState(1); const [status, setStatus] = useState(""); const [callId, setCallId] = useState("");
  const [since, setSince] = useState(""); const [until, setUntil] = useState("");
  const [selected, setSelected] = useState<Recording | null>(null); const [deleting, setDeleting] = useState<Recording | null>(null);
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const allowed = can("voice_assistant:recordings", "view");
  const records = useQuery({ queryKey: ["voice", userId, "recordings", page, status, callId, since, until], queryFn: () => getRecordings(page, status, callId, since, until), enabled: allowed, refetchInterval: 15000 });
  const currentSelection = records.data?.items.find(item => item.id === selected?.id) ?? selected;
  async function refresh() { await client.invalidateQueries({ queryKey: ["voice", userId, "recordings"] }); await client.invalidateQueries({ queryKey: ["voice", userId, "dashboard"] }); }
  if (!allowed) return <p>You need the voice recordings View permission.</p>;
  return <div className="space-y-5">
    <p className="text-sm">This library stores real imported WAV artifacts linked to ended calls. Importing audio does not mean the CRM captured a live telephone call. Live capture and automatic transcription remain blocked.</p>
    <ErrorBanner message={error ?? (records.error ? getErrorMessage(records.error) : null)} />
    <p>Private storage: {records.data?.storage ?? "checking"} · Live capture: {records.data?.live_capture ?? "unknown"} · Speech engine: {records.data?.transcription_engine ?? "unknown"}</p>
    {can("voice_assistant:recordings", "create") && <form className="bg-card rounded-xl border p-5 space-y-3" onSubmit={async event => {
      event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const file = data.get("file");
      if (!(file instanceof File) || file.size > 20 * 1024 * 1024) { setError("Choose a WAV file no larger than 20 MB."); return; }
      data.set("idempotency_key", form.dataset.importKey ?? crypto.randomUUID().replaceAll("-", "")); form.dataset.importKey = String(data.get("idempotency_key"));
      setBusy(true); setError(null); setMessage("");
      try { const record = await importRecording(data); setMessage(`Artifact ${record.id}: ${record.status}.`); if (record.status === "completed") { form.reset(); delete form.dataset.importKey; } await refresh(); }
      catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
    }} onChange={event => { delete event.currentTarget.dataset.importKey; }}>
      <h2 className="font-semibold">Import authorized recording artifact</h2>
      <p className="text-sm">PCM 16-bit WAV · mono/stereo · 8/16/24/48 kHz · up to 20 MB and 30 minutes. Supply the evidence reference authorizing this use. Imported consent evidence is operator-attested and not independently verified.</p>
      <label className="block">Ended call ID<input name="call_id" required pattern="[a-f0-9]{24}" maxLength={24} className="block border rounded-lg p-2 w-full" /></label>
      <label className="block">Consent or policy evidence reference<input name="consent_reference" required minLength={5} maxLength={150} className="block border rounded-lg p-2 w-full" /></label>
      <label className="block">Retention days<input name="retention_days" type="number" required min={1} max={365} defaultValue={30} className="block border rounded-lg p-2" /></label>
      <label className="block">Recording WAV<input name="file" type="file" required accept=".wav,audio/wav" className="block mt-2" /></label>
      <Button type="submit" loading={busy} disabled={!records.data || records.data.storage === "not_configured"}>Import and verify artifact</Button>
      {records.data?.storage === "not_configured" && <p className="text-sm">The administrator must configure private encrypted storage before importing audio.</p>}
      {message && <p role="status">{message}</p>}
    </form>}
    <section aria-label="Recording library" className="space-y-3">
      <div className="flex flex-wrap gap-3"><label>Status<select value={status} onChange={e => { setStatus(e.target.value); setPage(1); }} className="block border rounded-lg p-2"><option value="">All</option>{["pending", "completed", "expired", "failed", "deletion_pending", "deleted"].map(s => <option key={s}>{s}</option>)}</select></label>
        <form onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const start = String(form.get("since") ?? ""); const end = String(form.get("until") ?? ""); setCallId(String(form.get("call_id") ?? "")); setSince(start ? `${start}T00:00:00Z` : ""); setUntil(end ? new Date(new Date(`${end}T00:00:00Z`).getTime() + 86400000).toISOString() : ""); setPage(1); }} className="flex flex-wrap gap-2 items-end"><label>Filter by call ID<input name="call_id" pattern="[a-f0-9]{24}" maxLength={24} className="block border rounded-lg p-2" /></label><label>Imported from (UTC)<input name="since" type="date" className="block border rounded-lg p-2" /></label><label>Imported through (UTC)<input name="until" type="date" className="block border rounded-lg p-2" /></label><Button type="submit" variant="secondary">Apply filter</Button></form>
      </div>
      {records.isPending && <p role="status">Loading recordings…</p>}
      {records.data?.items.length === 0 && <p>No recording artifacts match this view.</p>}
      {records.data?.items.map(record => <article key={record.id} className="bg-card rounded-xl border p-4 space-y-2">
        <h3 className="font-semibold break-all">Call {record.call_id}</h3><p>{record.status} · {record.direction} · {record.origin.replaceAll("_", " ")} · call provider {record.call_provider}</p>
        <p className="text-sm">Call outcome: {record.call_outcome ?? "unavailable"} · Language: {record.language ?? "unverified"}</p>
        <p className="text-sm">Verified artifact duration: {record.duration_seconds}s · {(record.size_bytes / 1024).toFixed(1)} KB · {record.sample_rate} Hz · {record.channels} channel(s)</p>
        <p className="text-sm">Imported: {new Date(record.created_at).toLocaleString()} · Expires: {new Date(record.expires_at).toLocaleString()} · Transcript: {record.transcript_status}</p>
        <div className="flex flex-wrap gap-2"><Button variant="secondary" disabled={record.status !== "completed"} onClick={() => setSelected(record)}>Open audio and transcript</Button>
          {can("voice_assistant:recordings", "download") && <Button variant="secondary" disabled={record.status !== "completed" || busy} onClick={async () => {
            setBusy(true); setError(null);
            try { const blob = await getRecordingAudio(record.id, true); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `recording-${record.id}.wav`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
            catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
          }}>Download</Button>}
          {can("voice_assistant:recordings", "delete") && <Button variant="danger" disabled={record.status === "deleted" || busy} onClick={() => setDeleting(record)}>Delete artifact and transcript</Button>}
          {can("voice_assistant:recordings", "edit") && ["pending", "failed"].includes(record.status) && <Button variant="secondary" disabled={busy} onClick={async () => {
            setBusy(true); setError(null); try { await recoverRecording(record); await refresh(); } catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
          }}>Recover stored artifact</Button>}
        </div>
      </article>)}
      <div className="flex gap-3 items-center"><Button variant="secondary" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</Button><span>Page {page}</span><Button variant="secondary" disabled={page * 25 >= (records.data?.total ?? 0)} onClick={() => setPage(p => p + 1)}>Next</Button></div>
    </section>
    {currentSelection && currentSelection.status === "completed" && new Date(currentSelection.expires_at).getTime() > Date.now() && <RecordingViewer key={`${userId}:${currentSelection.id}:${currentSelection.version}`} record={currentSelection} editable={can("voice_assistant:recordings", "edit")} onClose={() => setSelected(null)} onSaved={async () => { setSelected(null); await refresh(); }} />}
    <ConfirmDialog open={!!deleting} title="Delete recording artifact?" message="Permanently delete the encrypted audio and linked transcript. Playback is disabled during deletion. Minimal audit metadata is retained." confirmLabel="Delete permanently" confirmVariant="danger" onClose={() => setDeleting(null)} onConfirm={async () => {
      if (!deleting) return; setError(null);
      try { await deleteRecording(deleting); if (selected?.id === deleting.id) setSelected(null); setDeleting(null); await refresh(); } catch (err) { setError(getErrorMessage(err)); }
    }} />
  </div>;
}

function RecordingViewer({ record, editable, onClose, onSaved }: { record: Recording; editable: boolean; onClose: () => void; onSaved: () => Promise<void> }) {
  const [url, setUrl] = useState<string | null>(null); const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const [segments, setSegments] = useState(""); const audio = useRef<HTMLAudioElement>(null); const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  return <section className="bg-card rounded-xl border p-5 space-y-3" aria-label="Recording detail">
    <h2 className="font-semibold">Imported artifact {record.id}</h2><Button variant="ghost" onClick={onClose}>Close recording</Button>
    <ErrorBanner message={error} />
    <div className="flex flex-wrap gap-2"><Button disabled={busy || !!url} onClick={async () => {
      setBusy(true); setError(null);
      try { const blob = await getRecordingAudio(record.id); if (alive.current) setUrl(URL.createObjectURL(blob)); }
      catch (err) { if (alive.current) setError(getErrorMessage(err)); } finally { if (alive.current) setBusy(false); }
    }}>Load authorized audio</Button><Button variant="secondary" disabled={busy || record.transcript_status === "not_available"} onClick={async () => {
      setBusy(true); setError(null);
      try { const result = await getTranscript(record.id); if (alive.current) setTranscript(result); }
      catch (err) { if (alive.current) setError(getErrorMessage(err)); } finally { if (alive.current) setBusy(false); }
    }}>Load recognized transcript</Button></div>
    {url && <><audio ref={audio} controls src={url} aria-label="Authorized recording playback" onError={() => setError("Audio playback failed. Reload the artifact or contact the storage operator.")} /><label className="block">Playback speed<select defaultValue="1" onChange={e => { if (audio.current) audio.current.playbackRate = Number(e.target.value); }} className="block border rounded-lg p-2">{[0.75, 1, 1.25, 1.5, 2].map(speed => <option key={speed} value={speed}>{speed}×</option>)}</select></label></>}
    {transcript && <div className="space-y-2"><h3 className="font-semibold">Recognized words supplied by operator</h3><p className="text-sm">{transcript.recognizer_label} · {transcript.language} · {transcript.provenance.replaceAll("_", " ")} · Summary: {transcript.summary_status}</p>{transcript.segments.map((segment, i) => <div key={i} className="border-t py-2"><Button variant="ghost" disabled={!url} onClick={() => { if (audio.current) audio.current.currentTime = segment.start_seconds; }}>Seek to {segment.start_seconds}s</Button><p className="text-sm">{segment.speaker} · {segment.start_seconds}–{segment.end_seconds}s{segment.confidence != null ? ` · confidence ${segment.confidence}` : ""}</p><p>{segment.text}</p></div>)}</div>}
    {editable && <form className="space-y-3 border-t pt-3" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError(null); const form = new FormData(event.currentTarget);
      try { const parsed = JSON.parse(segments) as Transcript["segments"]; if (!Array.isArray(parsed)) { setError("Supply a JSON array of recognized segments."); return; } await saveTranscript(record, { language: String(form.get("language")), recognizer_label: String(form.get("recognizer_label")), segments: parsed }); if (alive.current) await onSaved(); }
      catch (err) { if (alive.current) setError(err instanceof SyntaxError ? "Invalid transcript JSON. Supply a segment array." : getErrorMessage(err)); } finally { if (alive.current) setBusy(false); }
    }}><h3 className="font-semibold">Import existing recognized transcript</h3><p className="text-sm">Import actual recognition output with speaker, start_seconds, end_seconds and text. Provenance remains operator-supplied and unverified. No automatic transcription or AI summary is generated.</p>
      <label className="block">Recognition source label<input name="recognizer_label" required minLength={3} maxLength={80} className="block border rounded-lg p-2 w-full" /></label><label className="block">Transcript language<input name="language" defaultValue="en" required pattern="[a-z]{2}" maxLength={2} className="block border rounded-lg p-2" /></label>
      <label className="block">Recognized segments JSON<textarea required rows={6} maxLength={300000} value={segments} onChange={e => setSegments(e.target.value)} className="block border rounded-lg p-2 w-full" /></label><Button type="submit" loading={busy}>Store transcript with provenance</Button>
    </form>}
  </section>;
}
