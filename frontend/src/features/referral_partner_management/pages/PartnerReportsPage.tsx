import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest, apiRequestRaw, getAccessToken } from "@/shared/api/client";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Modal } from "@/components/overlays/Modal";
import { listReferralPartners } from "../api";

type Report = { summary?: Record<string,{reference:string;referrals:number;eligible_disbursed_amount:number}[]>; columns: { key: string; label: string }[]; rows: Record<string, string | number | null>[] };
export function PartnerReportsPage() {
  const [links,setLinks]=useState<{id:string;partner_id:string;referral_id:string;status:string;expires_at:string}[]>([]);
  const [linkPage,setLinkPage]=useState(1);
  const [linkTotal,setLinkTotal]=useState(0);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [partnerSearch,setPartnerSearch]=useState("");
  const [partners, setPartners] = useState<{ id: string; full_name: string }[]>([]);
  const [products, setProducts] = useState<{ id: string; name: string }[]>([]);
  const [report, setReport] = useState<Report>({ columns: [], rows: [] });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [page, setPage] = useState(1);
  const [target, setTarget] = useState<Report["rows"][number] | null>(null);
  const [replacement, setReplacement] = useState("");
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  useEffect(() => {void apiRequest<{id:string;name:string}[]>("/loan-products").then(setProducts).catch(e=>setError(e.message));},[]);
  useEffect(() => {let current=true;void listReferralPartners({page_size:100,search:partnerSearch||undefined}).then(result=>{if(current)setPartners(result.data);}).catch(e=>{if(current)setError(e.message);});return()=>{current=false;};},[partnerSearch]);
  useEffect(()=>{void apiRequestRaw<typeof links>(`/partner-management/links?page=${linkPage}&page_size=20&partner_id=${encodeURIComponent(filters.partner_id??"")}`).then(response=>{setLinks(response.data??[]);setLinkTotal(response.meta?.pagination?.total??0);}).catch(e=>setError(e.message));},[linkPage,filters.partner_id,revision]);
  const query = new URLSearchParams(Object.fromEntries(Object.entries(filters).filter(([, value]) => value))).toString();
  useEffect(() => {
    let current = true; setLoading(true); setError(null); setPage(1);
    void apiRequest<Report>(`/partner-management/report?${query}`).then(value => { if (current) setReport(value); }).catch(e => { if (current) setError(e.message); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [query, revision]);
  const select = (key: string, label: string, options: { value: string; label: string }[]) => <label className="text-sm" key={key}>{label}<select aria-label={label} className="mt-1 block w-full rounded-xl border border-border bg-card p-2" value={filters[key] ?? ""} onChange={e => setFilters({ ...filters, [key]: e.target.value })}><option value="">All</option>{options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>;
  const download = async () => {
    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}/partner-management/report?${query}&export=true`, { headers: { Authorization: `Bearer ${getAccessToken()}` } });
      if (!response.ok) throw new Error("Unable to export. Narrow the filters or check access.");
      const url = URL.createObjectURL(await response.blob()); const a = document.createElement("a"); a.href = url; a.download = "partner-referral-report.csv"; a.click(); URL.revokeObjectURL(url);
    } catch (e) { setError(e instanceof Error ? e.message : "Export failed."); }
  };
  return <section className="space-y-5 p-4"><h1 className="text-2xl font-semibold">Partner referrals and finance report</h1><ErrorBanner message={error} />
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><FormField label="From referral date" type="date" value={filters.start ?? ""} onChange={e => setFilters({ ...filters, start: e.target.value })} /><FormField label="Through referral date" type="date" value={filters.end ?? ""} onChange={e => setFilters({ ...filters, end: e.target.value })} />
      <FormField label="Search report Partners" value={partnerSearch} onChange={e=>setPartnerSearch(e.target.value)}/>{select("partner_id", "Partner", [...(filters.partner_id&&!partners.some(partner=>partner.id===filters.partner_id)?[{value:filters.partner_id,label:`Selected Partner ${filters.partner_id}`}]:[]),...partners.map(p => ({ value: p.id, label: p.full_name }))])}
      {select("product_id", "Product", products.map(p => ({ value: p.id, label: p.name })))}
      {select("origin", "Referral source", ["manual", "link"].map(value => ({ value, label: value })))}
      {select("application_status", "Application status", ["draft", "submitted"].map(value => ({ value, label: value })))}
      {select("disbursement_status", "Disbursement status", ["disbursed", "send_for_disbursement", "rejected"].map(value => ({ value, label: value })))}
      {select("commission_status", "Commission status", ["pending", "approved", "on_hold", "paid"].map(value => ({ value, label: value })))}
    </div><Button variant="secondary" disabled={loading} onClick={() => void download()}>Export report CSV</Button>
    {report.summary&&<div className="grid gap-4 lg:grid-cols-2">{Object.entries(report.summary).map(([name,groups])=><section key={name} className="overflow-x-auto rounded-xl border border-border bg-card p-4"><h2 className="font-semibold">{name==="partner_referrals"?"Partner-wise referrals and disbursements":"Product-wise referrals and disbursements"}</h2><table className="w-full text-sm"><thead><tr><th className="p-2 text-left">Reference</th><th className="p-2">Referrals</th><th className="p-2">Actual disbursed</th></tr></thead><tbody>{groups.map(group=><tr key={group.reference}><td className="p-2">{partners.find(p=>p.id===group.reference)?.full_name??products.find(p=>p.id===group.reference)?.name??group.reference}</td><td className="p-2">{group.referrals}</td><td className="p-2">{group.eligible_disbursed_amount.toLocaleString("en-IN")}</td></tr>)}</tbody></table></section>)}</div>}
    <p className="text-sm text-textSecondary">The date range selects referral creation dates. Amounts show persisted lifetime financial totals for those referrals. Original earnings and payments retain their Partner when attribution is corrected.</p>
    {loading ? <p role="status">Loading report…</p> : <div className="overflow-x-auto rounded-xl border border-border bg-card"><table className="w-full text-sm"><thead><tr>{report.columns.map(c => <th key={c.key} className="whitespace-nowrap p-3 text-left">{c.label}</th>)}<th className="p-3">Actions</th></tr></thead><tbody>{report.rows.slice((page - 1) * 20, page * 20).map(row => <tr key={row.application_id} className="border-t border-border">{report.columns.map(c => <td className="p-3" key={c.key}>{String(row[c.key] ?? "—")}</td>)}<td className="space-y-2 p-3"><Link className="text-primary underline" to={`/applications/${row.application_id}`}>View Application</Link><Button size="sm" variant="secondary" onClick={() => { setTarget(row); setReason(""); setReplacement(""); setAcknowledged(false); }}>Correct attribution</Button></td></tr>)}</tbody></table>{!report.rows.length && <p className="p-4">No matching referrals.</p>}</div>}
    <div className="flex gap-3"><Button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><span>{report.rows.length} referrals · Page {page}</span><Button disabled={page * 20 >= report.rows.length} onClick={() => setPage(page + 1)}>Next</Button></div>
    <section className="space-y-3 rounded-xl border border-border bg-card p-4"><h2 className="font-semibold">Referral links</h2>{links.map(link=><div className="flex flex-wrap items-center gap-3 border-b border-border py-2" key={link.id}><span>{partners.find(partner=>partner.id===link.partner_id)?.full_name??link.partner_id} - {link.referral_id} - {new Date(link.expires_at)<new Date()?"Expired":link.status}</span>{["active","used"].includes(link.status)&&<Button size="sm" variant="secondary" onClick={()=>{void apiRequest(`/partner-management/links/${link.id}/revoke`,{method:"POST"}).then(()=>setRevision(value=>value+1)).catch(e=>setError(e.message));}}>Revoke link</Button>}</div>)}{!links.length&&<p>No referral links.</p>}<div className="flex gap-3"><Button disabled={linkPage===1} onClick={()=>setLinkPage(linkPage-1)}>Previous links</Button><span>Page {linkPage}</span><Button disabled={linkPage*20>=linkTotal} onClick={()=>setLinkPage(linkPage+1)}>Next links</Button></div></section>
    {target && <Modal open onClose={() => setTarget(null)} title="Correct referral attribution"><form className="space-y-4" onSubmit={e => { e.preventDefault(); setLoading(true); void apiRequest(`/partner-management/referrals/${target.application_id}/attribution`, { method: "PUT", body: JSON.stringify({ version: target.version, partner_id: replacement, reason, acknowledge_financial_history: acknowledged }) }).then(() => { setTarget(null); setRevision(value => value + 1); }).catch(e => setError(e.message)).finally(() => setLoading(false)); }}><ErrorBanner message={error} /><label>Replacement Partner<select required className="block w-full rounded border p-2" value={replacement} onChange={e => setReplacement(e.target.value)}><option value="">Select</option>{partners.filter(p => p.id !== target.partner_id).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}</select></label><FormField label="Correction reason" required minLength={3} value={reason} onChange={e => setReason(e.target.value)} /><label className="flex gap-2"><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} />I acknowledge that existing earnings and payments remain unchanged and require separate financial review</label><Button type="submit" loading={loading} disabled={!acknowledged}>Save audited correction</Button></form></Modal>}
  </section>;
}
