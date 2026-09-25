import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { Drawer } from "@/components/overlays/Drawer";
import { Pagination } from "@/components/tables/Pagination";
import { formatINR } from "@/features/dashboard/format";
import {
  getAdvisorWork, getAnalyticsOverview, getProductWork, listAdvisorAnalytics, listProductAnalytics,
  type AdvisorAnalyticsRow, type AdvisorWork, type AnalyticsFilters, type AnalyticsOverview,
  type ProductAnalyticsRow, type ProductWork,
} from "@/features/insurance_management/analyticsApi";
import { INSURANCE_STATUS_LABELS } from "@/features/insurance_management/statusControl";
import { getErrorMessage } from "@/shared/api/errors";

const STAGE_ROUTES: Record<string, string> = {
  fresh_lead: "fresh-leads", policy_document: "policy-document", policy_login: "policy-login",
  payment: "payment", policy_issued: "policy-issued", re_eligible: "re-eligible",
  rejected: "rejected", on_hold: "on-hold",
};

function iso(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
function presetDates(value: string): Pick<AnalyticsFilters, "date_from" | "date_to"> {
  if (value === "all" || value === "custom") return {};
  const today = new Date();
  const end = iso(today);
  if (value === "today") return { date_from: end, date_to: end };
  if (value === "this_week") { const start = new Date(today); start.setDate(today.getDate() - ((today.getDay() + 6) % 7)); return { date_from: iso(start), date_to: end }; }
  if (value === "last_month") { const start = new Date(today.getFullYear(), today.getMonth() - 1, 1); const last = new Date(today.getFullYear(), today.getMonth(), 0); return { date_from: iso(start), date_to: iso(last) }; }
  return { date_from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), date_to: end };
}

const PAGE_SIZE = 10;

export function InsuranceAnalyticsPage() {
  const navigate = useNavigate();
  const [preset, setPreset] = useState("this_month");
  const [filters, setFilters] = useState<AnalyticsFilters>(presetDates("this_month"));
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [advisors, setAdvisors] = useState<AdvisorAnalyticsRow[]>([]);
  const [products, setProducts] = useState<ProductAnalyticsRow[]>([]);
  const [advisorPage, setAdvisorPage] = useState(1);
  const [productPage, setProductPage] = useState(1);
  const [advisorTotal, setAdvisorTotal] = useState(0);
  const [productTotal, setProductTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [advisorWork, setAdvisorWork] = useState<AdvisorWork | null>(null);
  const [productWork, setProductWork] = useState<ProductWork | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailType, setDetailType] = useState<"advisor" | "product" | null>(null);
  const [advisorDetailPage, setAdvisorDetailPage] = useState(1);
  const [productDetailPage, setProductDetailPage] = useState(1);
  const [advisorWorkTotal, setAdvisorWorkTotal] = useState(0);
  const [productWorkTotal, setProductWorkTotal] = useState(0);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const nextOverview = await getAnalyticsOverview(filters);
      setOverview(nextOverview);
      const [advisorResult, productResult] = await Promise.all([
        nextOverview.capabilities.advisor_business ? listAdvisorAnalytics(filters, advisorPage) : Promise.resolve({ data: [], pagination: null }),
        nextOverview.capabilities.policy_pipeline ? listProductAnalytics(filters, productPage) : Promise.resolve({ data: [], pagination: null }),
      ]);
      setAdvisors(advisorResult.data); setAdvisorTotal(advisorResult.pagination?.total ?? 0);
      setProducts(productResult.data); setProductTotal(productResult.pagination?.total ?? 0);
    } catch (err) { setError(getErrorMessage(err)); }
    finally { setLoading(false); }
  }, [advisorPage, filters, productPage]);

  useEffect(() => { void load(); }, [load]);
  const updateFilter = (key: keyof AnalyticsFilters, value: string) => { setAdvisorPage(1); setProductPage(1); setFilters((current) => ({ ...current, [key]: value || undefined })); };
  const changePreset = (value: string) => { setPreset(value); if (value !== "custom") setFilters((current) => ({ ...current, ...presetDates(value), date_from: presetDates(value).date_from, date_to: presetDates(value).date_to })); };
  const cards = useMemo(() => overview ? [
    ["Total Advisors", overview.summary.total_advisors], ["Total Business", overview.summary.total_business],
    ["Business Premium", overview.summary.business_premium == null ? null : formatINR(overview.summary.business_premium)],
    ["Policy Leads", overview.summary.total_policy_leads], ["Policy Issued", overview.summary.total_policy_issued],
    ["Recorded Policy Premium", overview.summary.policy_premium == null ? null : formatINR(overview.summary.policy_premium)],
  ].filter((item) => item[1] !== null) : [], [overview]);

  const openAdvisor = async (id: string, page = 1) => { setDetailType("advisor"); setDetailLoading(true); if (page === 1) setAdvisorWork(null); try { const result = await getAdvisorWork(id, filters, page); setAdvisorWork(result.data); setAdvisorDetailPage(page); setAdvisorWorkTotal(result.pagination?.total ?? result.data.businesses.length); } catch (err) { setDetailType(null); setError(getErrorMessage(err)); } finally { setDetailLoading(false); } };
  const openProduct = async (id: string, page = 1) => { setDetailType("product"); setDetailLoading(true); if (page === 1) setProductWork(null); try { const result = await getProductWork(id, filters, page); setProductWork(result.data); setProductDetailPage(page); setProductWorkTotal(result.pagination?.total ?? result.data.leads.length); } catch (err) { setDetailType(null); setError(getErrorMessage(err)); } finally { setDetailLoading(false); } };

  return <div className="space-y-6 p-4 sm:p-6">
    <header><h1 className="text-2xl font-bold text-text">Insurance Analytics</h1><p className="mt-1 text-sm text-textSecondary">Advisor business and policy pipeline reporting remain separate and drill into existing records.</p></header>
    <section className="rounded-card border border-border bg-card p-4 shadow-card" aria-label="Analytics filters">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <label className="text-xs font-medium text-textSecondary">Date Range<select aria-label="Date Range" value={preset} onChange={(e) => changePreset(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-text"><option value="all">All Time</option><option value="today">Today</option><option value="this_week">This Week</option><option value="this_month">This Month</option><option value="last_month">Last Month</option><option value="custom">Custom Range</option></select></label>
        <label className="text-xs font-medium text-textSecondary">Advisor<select aria-label="Advisor" value={filters.advisor_id ?? ""} onChange={(e) => updateFilter("advisor_id", e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2.5 text-sm"><option value="">All Advisors</option>{overview?.advisors.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <label className="text-xs font-medium text-textSecondary">Product <span className="font-normal">(policy leads)</span><select aria-label="Product" value={filters.product_id ?? ""} onChange={(e) => updateFilter("product_id", e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2.5 text-sm"><option value="">All Products</option>{overview?.products.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <label className="text-xs font-medium text-textSecondary">Stage <span className="font-normal">(policy leads)</span><select aria-label="Stage" value={filters.stage ?? ""} onChange={(e) => updateFilter("stage", e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2.5 text-sm"><option value="">All Stages</option>{overview?.stages.map((stage) => <option key={stage} value={stage}>{INSURANCE_STATUS_LABELS[stage] ?? stage}</option>)}</select></label>
      </div>
      {preset === "custom" && <div className="mt-3 flex flex-col gap-3 sm:flex-row"><label className="text-xs">From<input aria-label="From date" type="date" value={filters.date_from ?? ""} onChange={(e) => updateFilter("date_from", e.target.value)} className="ml-2 rounded-lg border border-border px-3 py-2" /></label><label className="text-xs">To<input aria-label="To date" type="date" value={filters.date_to ?? ""} onChange={(e) => updateFilter("date_to", e.target.value)} className="ml-2 rounded-lg border border-border px-3 py-2" /></label></div>}
      <p className="mt-3 text-xs text-text/50">Date uses business-added time for advisor work and policy-lead creation time for the pipeline; issued policies use their recorded Policy Issue Date. Product and Stage do not alter advisor-business totals.</p>
    </section>
    {error && <div role="alert" className="rounded-lg border border-danger/30 bg-danger/5 p-4 text-sm text-danger">{error} <button type="button" onClick={() => void load()} className="ml-2 font-semibold underline">Retry</button></div>}
    {loading ? <div aria-label="Loading insurance analytics" className="grid animate-pulse gap-3 sm:grid-cols-3">{Array.from({ length: 6 }, (_, i) => <div key={i} className="h-24 rounded-card bg-border/50" />)}</div> : overview && <>
      <section aria-labelledby="summary-heading"><h2 id="summary-heading" className="mb-3 text-lg font-semibold">Overall Summary</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">{cards.map(([label, value]) => <div key={String(label)} className="rounded-card border border-border bg-card p-4 shadow-card"><p className="text-xs font-medium text-textSecondary">{label}</p><p className="mt-2 text-xl font-bold text-text">{value}</p></div>)}</div></section>
      {overview.capabilities.advisor_business && <section className="rounded-card border border-border bg-card p-4 shadow-card" aria-labelledby="advisor-heading"><h2 id="advisor-heading" className="text-lg font-semibold">Advisor Business Analytics</h2><p className="mb-4 text-xs text-text/50">Counts and premium come only from Existing Business records.</p>{overview.summary.total_business === 0 ? <p className="py-8 text-center text-sm text-textSecondary">No advisor business records found for the selected filters.</p> : <div className="overflow-x-auto"><table className="min-w-[720px] w-full text-sm"><thead><tr className="border-b border-border text-left"><th className="py-3">Advisor</th><th>Businesses</th><th>Total Premium</th><th>Products</th><th className="text-right">Action</th></tr></thead><tbody>{advisors.map((row) => <tr key={row.advisor_id} className="border-b border-border/70"><td className="py-3 font-medium">{row.advisor_name}<span className="block text-xs text-text/45">{row.advisor_code}</span></td><td>{row.businesses}</td><td>{formatINR(row.total_premium)}</td><td>{row.products}</td><td className="text-right"><Button size="sm" variant="secondary" onClick={() => void openAdvisor(row.advisor_id)}>View Work</Button></td></tr>)}</tbody></table></div>}<Pagination page={advisorPage} totalPages={Math.max(1, Math.ceil(advisorTotal / PAGE_SIZE))} totalItems={advisorTotal} pageSize={PAGE_SIZE} itemLabel="advisors" onPageChange={setAdvisorPage} /></section>}
      {overview.capabilities.policy_pipeline && <><section aria-labelledby="pipeline-heading"><h2 id="pipeline-heading" className="mb-3 text-lg font-semibold">Policy Pipeline Analytics</h2>{overview.summary.total_policy_leads === 0 ? <p className="rounded-card border border-border bg-card py-8 text-center text-sm text-textSecondary shadow-card">No policy leads found for the selected filters.</p> : <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{overview.pipeline.map((item) => <button key={item.stage} type="button" onClick={() => navigate(`/insurance-management/${STAGE_ROUTES[item.stage]}`)} className="rounded-card border border-border bg-card p-4 text-left shadow-card transition hover:border-primary/40 hover:bg-primary/[0.03]"><span className="text-sm font-medium">{INSURANCE_STATUS_LABELS[item.stage] ?? item.stage}</span><span className="mt-2 block text-2xl font-bold text-primary">{item.count}</span></button>)}</div>}</section>
      <section className="rounded-card border border-border bg-card p-4 shadow-card" aria-labelledby="product-heading"><h2 id="product-heading" className="mb-4 text-lg font-semibold">Product Analytics</h2>{products.length === 0 ? <p className="py-8 text-center text-sm text-textSecondary">No product activity found for the selected filters.</p> : <div className="overflow-x-auto"><table className="min-w-[620px] w-full text-sm"><thead><tr className="border-b border-border text-left"><th className="py-3">Product</th><th>Leads</th><th>Issued</th><th>Recorded Premium</th></tr></thead><tbody>{products.map((row) => <tr key={row.product_id} className="border-b border-border/70"><td className="py-3"><button type="button" onClick={() => void openProduct(row.product_id)} className="font-semibold text-primary hover:underline">{row.product_name}</button></td><td>{row.leads}</td><td>{row.issued}</td><td>{formatINR(row.premium)}</td></tr>)}</tbody></table></div>}<Pagination page={productPage} totalPages={Math.max(1, Math.ceil(productTotal / PAGE_SIZE))} totalItems={productTotal} pageSize={PAGE_SIZE} itemLabel="products" onPageChange={setProductPage} /></section></>}
    </>}
    <Drawer open={detailType === "advisor"} onClose={() => { setDetailType(null); setAdvisorWork(null); setDetailLoading(false); }} title={advisorWork?.advisor.advisor_name ?? "Advisor Business Activity"}>
      {detailLoading && !advisorWork ? <p>Loading advisor work…</p> : advisorWork && <div className="space-y-5">
        <div className="grid grid-cols-2 gap-3"><Metric label="Businesses Added" value={advisorWork.advisor.businesses} /><Metric label="Total Premium" value={formatINR(advisorWork.advisor.total_premium)} /></div>
        <div><h3 className="font-semibold">Products</h3>{advisorWork.products.map((item) => <div key={item.product_name} className="flex justify-between border-b border-border py-2 text-sm"><span>{item.product_name}</span><span>{item.businesses}</span></div>)}</div>
        <div><h3 className="font-semibold">Customer / Business List</h3>{advisorWork.businesses.length === 0 ? <p className="py-4 text-sm text-textSecondary">No advisor business records found for the selected filters.</p> : advisorWork.businesses.map((item) => <button key={item.id} type="button" onClick={() => navigate(`/insurance-management/advisors/${advisorWork.advisor.advisor_id}`)} className="block w-full border-b border-border py-3 text-left text-sm hover:bg-background"><span className="font-medium">{item.customer_name ?? "Unnamed customer"}</span><span className="block text-xs text-textSecondary">{item.product_name} · {formatINR(item.premium)}</span></button>)}</div>
        <Pagination page={advisorDetailPage} totalPages={Math.max(1, Math.ceil(advisorWorkTotal / PAGE_SIZE))} totalItems={advisorWorkTotal} pageSize={PAGE_SIZE} itemLabel="businesses" onPageChange={(page) => void openAdvisor(advisorWork.advisor.advisor_id, page)} />
      </div>}
    </Drawer>
    <Drawer open={detailType === "product"} onClose={() => { setDetailType(null); setProductWork(null); setDetailLoading(false); }} title={productWork?.product.product_name ?? "Product Activity"}>
      {detailLoading && !productWork ? <p>Loading product activity…</p> : productWork && <div className="space-y-5">
        <div className="grid grid-cols-3 gap-2"><Metric label="Total Leads" value={productWork.product.leads} /><Metric label="Issued" value={productWork.product.issued} /><Metric label="Premium" value={formatINR(productWork.product.premium)} /></div>
        {productWork.leads.length === 0 ? <p className="py-4 text-sm text-textSecondary">No policy leads found for the selected filters.</p> : productWork.leads.map((item) => <div key={item.id} className="border-b border-border py-3 text-sm"><button type="button" onClick={() => navigate(`/insurance-cases/${item.id}`)} className="font-semibold text-primary hover:underline">{item.case_code}</button><button type="button" onClick={() => navigate(`/customers/${item.customer_id}`)} className="ml-2 hover:underline">{item.customer_name ?? "Unnamed customer"}</button><span className="block text-xs text-textSecondary">{item.advisor_name ?? "Unassigned"} · {INSURANCE_STATUS_LABELS[item.stage] ?? item.stage}</span></div>)}
        <Pagination page={productDetailPage} totalPages={Math.max(1, Math.ceil(productWorkTotal / PAGE_SIZE))} totalItems={productWorkTotal} pageSize={PAGE_SIZE} itemLabel="policy leads" onPageChange={(page) => void openProduct(productWork.product.product_id, page)} />
      </div>}
    </Drawer>
  </div>;
}

function Metric({ label, value }: { label: string; value: string | number }) { return <div className="rounded-lg bg-background p-3"><p className="text-xs text-textSecondary">{label}</p><p className="mt-1 font-bold text-text">{value}</p></div>; }
