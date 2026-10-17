import { useQuery } from "@tanstack/react-query";
import { NavLink, useParams } from "react-router-dom";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/shared/api/errors";
import { getDashboard } from "./api";
import { CallsPanel } from "./CallsPanel";
import { KnowledgePanel } from "./KnowledgePanel";
import { SettingsPanel } from "./SettingsPanel";
import { ProviderConnectionsScreen } from "./ProviderConnectionsScreen";
import { RecordingsPanel } from "./RecordingsPanel";
import { CampaignPanel } from "./CampaignPanel";
import { ContactPolicyPanel } from "./ContactPolicyPanel";

const sections = [
  ["dashboard", "Voice Dashboard"], ["live", "Live Calls"], ["incoming", "Incoming Calls"],
  ["outgoing", "Outgoing Calls"], ["history", "Call History"], ["knowledge", "AI Assist / Knowledge"],
  ["recordings", "Recordings & Transcripts"],
  ["studio", "Voice Studio"], ["campaigns", "Call Campaigns"], ["routing", "Call Routing"],
  ["schedules", "Schedules & Business Hours"], ["analytics", "Analytics & Reports"],
  ["compliance", "Compliance & Consent"], ["settings", "Settings"], ["providers", "Provider Connections"],
];
export function VoiceAssistantPage() {
  const { section = "dashboard" } = useParams(); const { userId } = useAuth();
  const dashboard = useQuery({ queryKey: ["voice", userId, "dashboard"], queryFn: getDashboard, refetchInterval: 10000 });
  const data = dashboard.data;
  const unavailable: Record<string, string> = {
    studio: "No voice provider is connected. Voice selection, audio previews and custom voice uploads remain unavailable until supported formats, malware scanning, storage, owner consent and provider verification are integrated.",
    routing: "Employee answer, rejection, timeout and transfer states can be tested in Incoming Calls. Real employee notifications, availability routing and browser audio require a verified telephony integration.",
    schedules: "Owner settings enforce same-day outgoing simulation hours and the configured timezone. Production campaign scheduling and holiday management are not yet available.",
  };
  return <SimplePageLayout title="AI Voice Assistant" subtitle="Call operations, reviewed knowledge and provider readiness">
    <div className="bg-primary/10 border border-primary/20 rounded-xl p-4 mb-5"><strong>Development framework · Live calling disabled</strong><p className="text-sm mt-1">Call records and call metrics are simulations. Live telephony, speech and capture are blocked. Imported audio artifacts are labelled separately.</p></div>
    <nav aria-label="Voice assistant sections" className="flex flex-wrap gap-2 mb-6">{sections.map(([key, label]) => <NavLink key={key} to={`/voice-assistant/${key}`} className={`rounded-lg px-3 py-2 text-sm border ${section === key ? "bg-primary text-white" : "bg-card text-text"}`}>{label}</NavLink>)}</nav>
    <ErrorBanner message={dashboard.error ? getErrorMessage(dashboard.error) : null} />
    {["dashboard", "analytics"].includes(section) && <>
      {dashboard.isPending && <p role="status">Loading voice metrics…</p>}
      {data && <><div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">{Object.entries(data.metrics).map(([key, value]) => <div className="bg-card rounded-xl border p-4" key={key}><p className="text-sm text-text/60 capitalize">{key.replaceAll("_", " ")}</p><p className="text-2xl font-semibold mt-2">{value}</p></div>)}</div><p className="my-4 text-sm">ARQ worker: {data.worker} · Cost estimate: unavailable · Simulations created today in the configured timezone; active includes earlier sessions. AI/human handled counts can overlap. Average seconds includes unanswered sessions; average answered seconds uses answered sessions only.</p><section className="bg-card rounded-xl border p-5"><h2 className="font-semibold mb-3">Recent simulated activity</h2>{data.recent.length ? data.recent.map(call => <p className="py-2 border-t text-sm" key={call.id}>{call.contact_label} · {call.direction} · {call.status} · {new Date(call.created_at).toLocaleString()}</p>) : <p>No call activity yet.</p>}</section></>}
    </>}
    {["live", "incoming", "outgoing", "history"].includes(section) && <CallsPanel key={`${userId}:${section}`} direction={section === "incoming" || section === "outgoing" ? section : ""} live={section === "live"} />}
    {section === "knowledge" && <KnowledgePanel key={userId} />}
    {section === "recordings" && <RecordingsPanel key={userId} />}
    {section === "campaigns" && <CampaignPanel key={userId} />}
    {section === "compliance" && <ContactPolicyPanel key={userId} />}
    {section === "settings" && <SettingsPanel />}
    {section === "providers" && <ProviderConnectionsScreen key={userId} />}
    {["dashboard", "analytics"].includes(section) && data?.operational && <section className="bg-card rounded-xl border p-5 space-y-3"><h2 className="font-semibold">Subsystem readiness and persisted processing counts</h2><p className="text-sm">Unavailable values are unverified; artifact counts do not imply live capture.</p><dl className="grid gap-3 sm:grid-cols-2">{Object.entries(data.operational).map(([key, value]) => <div key={key}><dt className="text-sm capitalize">{key.replaceAll("_", " ")}</dt><dd>{value == null ? "Unavailable" : typeof value === "object" ? Object.entries(value).map(([state, count]) => `${state}: ${count}`).join(" · ") : String(value).replaceAll("_", " ")}</dd></div>)}</dl></section>}
    {unavailable[section] && <div className="bg-card rounded-xl border p-5"><h2 className="font-semibold mb-2">Integration required</h2><p>{unavailable[section]}</p></div>}
    {section === "compliance" && <section className="bg-card rounded-xl border p-5 space-y-3"><h2 className="font-semibold">Activation prerequisites outstanding</h2><p>Selected telephony provider: {data?.provider.selected_provider ?? "loading"} · Sandbox: {data?.provider.sandbox ?? "unknown"}</p>{data?.provider.blockers.map(reason => <p key={reason}>{reason}</p>)}<p>Validated speech languages: none. Provider-hosted server-offline fallback: unverified.</p><p className="text-sm">There is no UI override for backend activation gates. Secrets and legal documents are not collected in ordinary text fields.</p></section>}
    {!sections.some(([key]) => key === section) && <p>Unknown voice section. Select a section above.</p>}
  </SimplePageLayout>;
}
