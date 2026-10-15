import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/useAuth";
import { usePermissions } from "@/features/access_control/usePermissions";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { TextareaField } from "@/components/forms/TextareaField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { getErrorMessage } from "@/shared/api/errors";
import { campaignAction, createCampaign, getCampaigns, importCampaignAudience, previewCampaign, stopCampaigns, type Campaign, type CampaignPreview } from "./api";

export function CampaignPanel() {
  const { userId, role } = useAuth(); const cache = useQueryClient();
  const { can, loading } = usePermissions();
  const mayView = can("voice_assistant.campaigns", "view");
  const mayCreate = can("voice_assistant.campaigns", "create");
  const mayEdit = can("voice_assistant.campaigns", "edit");
  const mayImport = can("voice_assistant.campaigns", "import");
  const [page, setPage] = useState(1); const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("service_callback"); const [objective, setObjective] = useState("");
  const [timezone, setTimezone] = useState("Asia/Kolkata"); const [selected, setSelected] = useState("");
  const [file, setFile] = useState<File | null>(null); const [importKey, setImportKey] = useState(() => crypto.randomUUID());
  const [preview, setPreview] = useState<CampaignPreview | null>(null); const [reason, setReason] = useState("");
  const query = useQuery({ queryKey: ["voice", userId, "campaigns", page], queryFn: () => getCampaigns(page), refetchInterval: 15000, enabled: mayView });
  const campaign = query.data?.items.find(item => item.id === selected);
  const mutation = useMutation({ mutationFn: async (operation: { kind: string; campaign?: Campaign }) => {
    if (operation.kind === "create") return createCampaign(name, purpose, objective, timezone);
    if (operation.kind === "stop") return stopCampaigns(reason);
    const current = operation.campaign ?? campaign;
    if (!current) throw new Error("Select a campaign first.");
    if (operation.kind === "preview") { setPreview(await previewCampaign(current.id)); return; }
    if (operation.kind === "import") {
      if (!file) throw new Error("Select a CSV file.");
      const data = new FormData(); data.set("file", file); data.set("version", String(current.version)); data.set("idempotency_key", importKey);
      return importCampaignAudience(current.id, data);
    }
    return campaignAction(current, operation.kind);
  }, onSuccess: () => cache.invalidateQueries({ queryKey: ["voice", userId, "campaigns"] }) });
  if (loading) return <p role="status">Loading campaign permissions...</p>;
  if (!mayView) return <p>Campaign View permission is required.</p>;
  return <section className="bg-card border border-border rounded-[12px] p-4 sm:p-5 space-y-4">
    <h2 className="font-semibold">Campaign eligibility dry runs</h2>
    <p className="text-sm text-textSecondary">No calls are placed. Test and production dispatch require verified transport, approved voice services, consent policy and staging acceptance. Maximum 10,000 recipients; this is a configured limit, not measured production capacity.</p>
    <ErrorBanner message={query.error || mutation.error ? getErrorMessage(query.error ?? mutation.error) : null} />
    <form className="grid gap-x-5 sm:grid-cols-2" onSubmit={event => { event.preventDefault(); mutation.mutate({ kind: "create" }); }}>
      <FormField label="Name" required minLength={3} maxLength={100} value={name} onChange={e => setName(e.target.value)} />
      <FormField label="Purpose identifier" required pattern="[a-z][a-z0-9_-]{2,49}" value={purpose} onChange={e => setPurpose(e.target.value)} />
      <div className="sm:col-span-2"><TextareaField label="Objective" required minLength={10} maxLength={2000} value={objective} onChange={e => setObjective(e.target.value)} /></div>
      <FormField label="IANA timezone" required value={timezone} onChange={e => setTimezone(e.target.value)} />
      <div className="flex items-end pb-4"><Button type="submit" disabled={mutation.isPending || !mayCreate}>Create dry-run campaign</Button></div>
    </form>
    {query.isPending && <p role="status">Loading campaigns...</p>}
    {query.data?.items.map(item => <article key={item.id} className="border rounded p-3 space-y-2">
      <button onClick={() => { setSelected(item.id); setPreview(null); setFile(null); setImportKey(crypto.randomUUID()); }}>{item.name}</button>
      <p>{item.status} · {item.timezone} · {item.mode}</p><p>{Object.entries(item.processing_counts).map(([state, count]) => `${state}: ${count}`).join(" · ")}</p>
      <div className="flex flex-wrap gap-2">{({ draft: ["validate", "cancel"], ready: ["start", "pause", "cancel"], running: ["pause", "cancel"], paused: ["validate", "resume", "cancel"], completed: ["archive"], cancelled: ["archive"] }[item.status] ?? []).map(action => <button className="border rounded p-2" key={action} disabled={mutation.isPending || !mayEdit} onClick={() => mutation.mutate({ kind: action, campaign: item })}>{action === "start" || action === "resume" ? `${action} dry run` : action}</button>)}</div>
    </article>)}
    <div className="flex items-center gap-3"><Button size="sm" variant="ghost" disabled={page === 1} onClick={() => { setPage(page - 1); setSelected(""); }}>Previous</Button><span className="text-sm">Page {page}</span><Button size="sm" variant="ghost" disabled={page * 25 >= (query.data?.total ?? 0)} onClick={() => { setPage(page + 1); setSelected(""); }}>Next</Button></div>
    {campaign && <div className="border rounded p-3 space-y-3"><h3>{campaign.name}: audience</h3><p>CSV: customer_id,timezone. Existing authorized CRM customers only; at most 500 rows per batch. Voice consent is separate from SMS preferences.</p>
      <input aria-label="Audience CSV" type="file" accept=".csv" onChange={e => { setFile(e.target.files?.[0] ?? null); setImportKey(crypto.randomUUID()); }} />
      <button disabled={mutation.isPending || !mayImport || !file || !["draft", "paused"].includes(campaign.status)} onClick={() => mutation.mutate({ kind: "import" })}>Import audience</button>
      <button disabled={mutation.isPending} onClick={() => mutation.mutate({ kind: "preview" })}>Preview eligibility (first 25)</button>
      {preview && <><p>Calls placed: {preview.calls_placed}. Production: {preview.production_dispatch}.</p>{preview.items.map(item => <p key={item.customer_id}>{item.customer_id}: {item.reason.replaceAll("_", " ")}</p>)}</>}
    </div>}
    {role === "owner" && <form onSubmit={e => { e.preventDefault(); mutation.mutate({ kind: "stop" }); }} className="border-t border-border pt-4"><FormField label="Emergency stop reason" required minLength={5} maxLength={160} value={reason} onChange={e => setReason(e.target.value)} /><Button type="submit" variant="danger" disabled={mutation.isPending}>Stop all campaign processing</Button><p className="mt-2 text-xs text-textSecondary">Pauses eligibility workers. No live call termination is available.</p></form>}
  </section>;
}
