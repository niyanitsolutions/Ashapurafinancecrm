import { useRef, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getErrorMessage } from "@/shared/api/errors";
import { policyReports, runPolicyReport } from "./api";

export function PolicyStudio() {
  const { isOwner } = usePermissions(); const [open, setOpen] = useState(false); const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null); const [data, setData] = useState<Awaited<ReturnType<typeof policyReports>> | null>(null); const [page, setPage] = useState(1);
  const pending = useRef<string | null>(null);
  if (!isOwner) return null;
  async function load(target: number) { setBusy(true); setError(null); try { setData(await policyReports(target)); setPage(target); setOpen(true); } catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); } }
  return <section className="bg-card border rounded-xl p-5 space-y-3" aria-label="Synthetic policy regression">
    <h2 className="font-semibold">Synthetic policy regression</h2>
    <p className="text-sm">Tests typed proposals against backend policy using built-in synthetic cases. No model, audio, provider, customer records or CRM actions are accessed. Passing does not approve a release or activate calling.</p>
    <ErrorBanner message={error} />
    <Button variant="secondary" disabled={busy} onClick={() => void load(1)}>Load policy test reports</Button>
    {open && data && <><Button disabled={busy} onClick={async () => {
      setBusy(true); setError(null); pending.current ??= crypto.randomUUID().replaceAll("-", "");
      try { await runPolicyReport(data.suite_version, pending.current); pending.current = null; setData(await policyReports(1)); setPage(1); }
      catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
    }}>Run synthetic policy suite</Button>
    {data.items.length === 0 && <p>No policy reports yet.</p>}
    {data.items.map(report => <article key={report.id} className="border rounded-lg p-3 space-y-2"><p>{report.passed ? "Policy checks passed" : "Policy checks failed"} · {new Date(report.created_at).toLocaleString()}</p><p className="text-sm">{report.suite_version} · {report.policy_version} · Activation ineligible</p><details><summary>Scenario results ({report.cases.length})</summary><ul className="text-sm space-y-2">{report.cases.map(item => <li key={item.name}>{item.name.replaceAll("_", " ")}: {item.passed ? "Pass" : "Fail"} · Expected response {item.expected_response_allowed ? "allowed" : "withheld"} · Actual {item.rejected ? "schema rejected" : item.actual.response_allowed ? "allowed" : "withheld"}{item.actual.reason ? ` · ${item.actual.reason.replaceAll("_", " ")}` : ""}</li>)}</ul></details></article>)}
    <div className="flex gap-2"><Button variant="secondary" disabled={busy || page === 1} onClick={() => void load(page - 1)}>Previous policy reports</Button><Button variant="secondary" disabled={busy || page * 10 >= data.total} onClick={() => void load(page + 1)}>Next policy reports</Button></div></>}
  </section>;
}
