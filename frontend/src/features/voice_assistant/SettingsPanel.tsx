import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/shared/api/errors";
import { getSettings, saveSettings, type VoiceSettings } from "./api";

export function SettingsPanel() {
  const { isOwner } = usePermissions(); const { userId } = useAuth();
  const config = useQuery({ queryKey: ["voice", userId, "settings"], queryFn: getSettings, enabled: isOwner });
  if (!isOwner) return <p>Voice settings are restricted to the Owner.</p>;
  if (config.error) return <ErrorBanner message={getErrorMessage(config.error)} />;
  if (!config.data) return <p role="status">Loading settings…</p>;
  return <SettingsForm key={config.data.version} initial={config.data} />;
}

function SettingsForm({ initial }: { initial: VoiceSettings }) {
  const { userId } = useAuth(); const client = useQueryClient();
  const [draft, setDraft] = useState(initial); const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); const [saved, setSaved] = useState(false);
  const numbers: { key: keyof VoiceSettings; label: string; min: number; max: number }[] = [
    { key: "ring_seconds", label: "Employee ring timeout (seconds)", min: 3, max: 120 },
    { key: "transfer_seconds", label: "Human transfer timeout (seconds)", min: 3, max: 120 },
    { key: "max_duration_seconds", label: "Maximum call duration (seconds)", min: 30, max: 1800 },
    { key: "max_concurrent_calls", label: "Concurrent mock calls", min: 1, max: 20 },
    { key: "daily_call_limit", label: "Daily mock call limit", min: 1, max: 1000 },
    { key: "monthly_minute_limit", label: "Monthly mock minute limit", min: 1, max: 10000 },
    { key: "calls_per_minute", label: "Mock calls per minute", min: 1, max: 60 },
  ];
  return <form className="bg-card border rounded-xl p-5 space-y-5" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError(null); setSaved(false);
    try { await saveSettings(draft); setSaved(true); await client.invalidateQueries({ queryKey: ["voice", userId] }); }
    catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
  }}>
    <ErrorBanner message={error} />
    <p className="text-sm text-text/70">These controls apply to the simulator. Saving them cannot activate live calls, recording or voice cloning. Automatic retries and call campaigns are unavailable.</p>
    <label className="block">Mode<select className="block border rounded-lg p-2" value={draft.mode} onChange={e => setDraft({ ...draft, mode: e.target.value as VoiceSettings["mode"] })}><option value="disabled">Disabled</option><option value="mock">Mock simulation</option></select></label>
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{numbers.map(field => <label key={field.key}>{field.label}<input required type="number" min={field.min} max={field.max} className="block w-full border rounded-lg p-2" value={Number(draft[field.key])} onChange={e => setDraft({ ...draft, [field.key]: Number(e.target.value) })} /></label>)}
      <label>Timezone<input required className="block border rounded-lg p-2 w-full" value={draft.timezone} onChange={e => setDraft({ ...draft, timezone: e.target.value })} /></label>
      <label>Calling window starts<input type="time" required className="block border rounded-lg p-2" value={draft.calling_start} onChange={e => setDraft({ ...draft, calling_start: e.target.value })} /></label>
      <label>Calling window ends<input type="time" required className="block border rounded-lg p-2" value={draft.calling_end} onChange={e => setDraft({ ...draft, calling_end: e.target.value })} /></label>
      <label>Default text language code<input required pattern="[a-z]{2}" className="block border rounded-lg p-2" value={draft.default_language} onChange={e => setDraft({ ...draft, default_language: e.target.value })} /></label>
    </div>
    <label className="block"><input type="checkbox" checked={draft.ai_fallback} onChange={e => setDraft({ ...draft, ai_fallback: e.target.checked })} /> Simulate AI fallback after employee timeout</label>
    <label className="block">Conversation behaviour<textarea required minLength={10} maxLength={4000} rows={4} className="block w-full border rounded-lg p-2" value={draft.conversation_instructions} onChange={e => setDraft({ ...draft, conversation_instructions: e.target.value })} /></label>
    <label className="block">Operational instructions<textarea required minLength={10} maxLength={4000} rows={4} className="block w-full border rounded-lg p-2" value={draft.operational_rules} onChange={e => setDraft({ ...draft, operational_rules: e.target.value })} /></label>
    <p className="text-sm">Backend safety policy always applies. Model testing has no CRM action tools.</p>
    <Button type="submit" loading={busy}>Save settings</Button>{saved && <p role="status">Settings saved.</p>}
  </form>;
}
