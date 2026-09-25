import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { listMetaLeadRoutings, saveMetaLeadRouting, setMetaLeadRoutingStatus, syncMetaLeadRoutings, type MetaLeadRouting, type MetaLeadRoutingInput } from "@/features/lead_capture/api";
import { insuranceCategoriesApi, insuranceProductsApi, leadSourcesApi, loanProductsApi, type InsuranceProduct, type NamedMasterData } from "@/features/system_settings/api";
import { getErrorMessage } from "@/features/system_settings/errors";
import { NamedMasterDataPage } from "@/features/system_settings/pages/NamedMasterDataPage";

type ProductCategory = "loan" | "insurance";
type ProductOption = { id: string; name: string };

export function LeadSourcesPage() {
  return <NamedMasterDataPage title="Lead Sources" createPlaceholder="e.g. Website" api={leadSourcesApi} renderEditExtension={(item) => <MetaRouting leadSource={item} />} />;
}

function MetaRouting({ leadSource }: { leadSource: NamedMasterData }) {
  const [routes, setRoutes] = useState<MetaLeadRouting[]>([]);
  const [loans, setLoans] = useState<ProductOption[]>([]);
  const [insurance, setInsurance] = useState<ProductOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const load = () => listMetaLeadRoutings().then(setRoutes);

  useEffect(() => {
    let active = true;
    Promise.all([listMetaLeadRoutings(), loanProductsApi.list(), insuranceProductsApi.list(), insuranceCategoriesApi.list()]).then(([r, lp, ip, cats]) => {
      if (!active) return;
      const activeCats = new Set(cats.filter((c) => c.status === "active").map((c) => c.id));
      setRoutes(r);
      setLoans(lp.filter((p) => p.status === "active").map(toProductOption));
      setInsurance(ip.filter((p) => p.status === "active" && p.category_id && activeCats.has(p.category_id)).map(toProductOption));
    }).catch((err) => active && setError(getErrorMessage(err)));
    return () => { active = false; };
  }, [leadSource.id]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setError(null); setMessage(null); setSaving(true);
    try { await action(); await load(); setMessage(success); }
    catch (err) { setError(getErrorMessage(err)); }
    finally { setSaving(false); }
  };

  return <div className="rounded-xl border border-border bg-background p-4">
    <div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-semibold">Meta Lead Routing</h3><p className="mt-1 text-xs text-text/60">Each immutable Meta Form ID has its own route. Unconfigured forms are held safely for retry.</p></div><Button size="sm" variant="secondary" disabled={saving} onClick={() => run(syncMetaLeadRoutings, "Meta forms synchronized. Existing routes were preserved.")}>Sync Forms</Button></div>
    <ErrorBanner message={error} />{message && <p className="mt-3 text-sm text-success">{message}</p>}
    <div className="mt-4 space-y-4">{routes.length === 0 && <p className="text-sm text-text/50">No synchronized Meta forms yet. Select Sync Forms.</p>}{routes.map((route) => <RouteEditor key={route.meta_form_id} route={route} loans={loans} insurance={insurance} disabled={saving} onSave={(payload) => run(() => saveMetaLeadRouting(route.meta_form_id, payload), `Routing saved for ${route.form_name}.`)} onStatus={(active) => run(() => setMetaLeadRoutingStatus(route.meta_form_id, active), `Routing ${active ? "activated" : "deactivated"}.`)} />)}</div>
  </div>;
}

function RouteEditor({ route, loans, insurance, disabled, onSave, onStatus }: { route: MetaLeadRouting; loans: ProductOption[]; insurance: ProductOption[]; disabled: boolean; onSave: (p: MetaLeadRoutingInput) => void; onStatus: (active: boolean) => void }) {
  const [category, setCategory] = useState<ProductCategory>(route.category ?? "loan");
  const [mode, setMode] = useState<"default" | "customer_answer">(route.product_mode ?? "default");
  const [productId, setProductId] = useState(route.default_product_id ?? "");
  const [question, setQuestion] = useState(route.product_question_key ?? route.product_question_label ?? "");
  const [mappings, setMappings] = useState<[string, string][]>(Object.entries(route.answer_mappings));
  const products = category === "loan" ? loans : insurance;
  const cls = "mt-1 block w-full rounded-xl border border-border bg-card px-3 py-2 text-sm";
  const changeCategory = (value: ProductCategory) => { setCategory(value); setProductId(""); setMappings((rows) => rows.map(([answer]) => [answer, ""])); };
  const answerMappings = Object.fromEntries(mappings.filter(([answer, product]) => answer.trim() && product));
  const payload: MetaLeadRoutingInput = { form_name: route.form_name, category, product_mode: mode, default_product_id: mode === "default" ? productId : null, destination_module: category === "loan" ? "leads" : "insurance_policy_leads", destination_type: category === "loan" ? "fresh_leads" : "fresh_lead", product_question_key: mode === "customer_answer" ? question : null, product_question_label: null, answer_mappings: mode === "customer_answer" ? answerMappings : {}, active: true };
  const valid = mode === "default" ? Boolean(productId) : Boolean(question && Object.keys(answerMappings).length);

  return <div className="rounded-xl border border-border bg-card p-4">
    <div className="flex justify-between gap-3"><div><p className="font-medium">{route.form_name}</p><p className="font-mono text-xs text-text/50">Form ID: {route.meta_form_id}</p></div><span className={`rounded-full px-2 py-1 text-xs ${route.status === "active" ? "bg-success/10 text-success" : "bg-warning/10 text-warning"}`}>{route.status.replace(/_/g, " ")}</span></div>
    <div className="mt-3 grid gap-3 md:grid-cols-3">
      <label className="text-xs">Category<select aria-label={`${route.form_name} Category`} value={category} onChange={(e) => changeCategory(e.target.value as ProductCategory)} className={cls}><option value="loan">Loan</option><option value="insurance">Insurance</option></select></label>
      <label className="text-xs">Product Mode<select aria-label={`${route.form_name} Product Mode`} value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} className={cls}><option value="default">Default Product</option><option value="customer_answer">Customer Answer</option></select></label>
      <label className="text-xs">Destination<input readOnly value={category === "loan" ? "Leads -> Fresh Leads" : "Insurance -> Policy Leads -> Fresh Leads"} className={cls} /></label>
    </div>
    {mode === "default" ? <label className="mt-3 block text-xs">Default Product<select aria-label={`${route.form_name} Default Product`} value={productId} onChange={(e) => setProductId(e.target.value)} className={cls}><option value="">Select active product</option>{products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label> : <div className="mt-3 space-y-3"><label className="block text-xs">Product Question<input aria-label={`${route.form_name} Product Question`} list={`q-${route.id}`} value={question} onChange={(e) => setQuestion(e.target.value)} className={cls} /><datalist id={`q-${route.id}`}>{route.discovered_questions.map((q) => <option key={q} value={q} />)}</datalist></label><div><p className="text-xs">Answer Mappings</p>{mappings.map(([answer, mapped], i) => <div key={i} className="mt-2 grid grid-cols-[1fr_1fr_auto] gap-2"><input aria-label={`Answer ${i + 1}`} placeholder="Meta answer" value={answer} onChange={(e) => setMappings((rows) => rows.map((row, j) => j === i ? [e.target.value, row[1]] : row))} className={cls} /><select aria-label={`Mapped product ${i + 1}`} value={mapped} onChange={(e) => setMappings((rows) => rows.map((row, j) => j === i ? [row[0], e.target.value] : row))} className={cls}><option value="">Select product</option>{products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select><button type="button" aria-label={`Remove mapping ${i + 1}`} onClick={() => setMappings((rows) => rows.filter((_, j) => j !== i))} className="mt-1 px-2 text-danger">x</button></div>)}<Button size="sm" variant="secondary" className="mt-2" onClick={() => setMappings((rows) => [...rows, ["", ""]])}>+ Add Mapping</Button></div></div>}
    <div className="mt-4 flex gap-2"><Button size="sm" disabled={disabled || !valid} onClick={() => onSave(payload)}>Save Routing</Button>{route.status === "active" ? <Button size="sm" variant="secondary" disabled={disabled} onClick={() => onStatus(false)}>Deactivate</Button> : route.status === "inactive" ? <Button size="sm" variant="secondary" disabled={disabled} onClick={() => onStatus(true)}>Activate</Button> : null}</div>
  </div>;
}

function toProductOption(product: NamedMasterData | InsuranceProduct): ProductOption { return { id: product.id, name: product.name }; }
