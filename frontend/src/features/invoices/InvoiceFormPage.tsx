import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/shared/api/errors";
import { calculateItems } from "./calculations";
import { getCustomers, getDefaults, getInvoice, money, previewPdf, saveInvoice, type Company, type CustomerOption, type InvoiceInput, type Item } from "./api";

const blankItem = (gst="18"): Item => ({description:"",hsn:"",quantity:"1",unit:"nos.s",rate:"0",gst_rate:gst});
function empty(): InvoiceInput {
  const today = new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata"}).format(new Date());
  return {customer_id:null,customer:{name:"",address:"",city:"",state:"",pincode:"",country:"India",gstin:"",phone:"",email:""},invoice_date:today,due_date:today,place_of_supply:"",terms:"",tax_type:"IGST",items:[blankItem()],version:1};
}
const inputClass = "w-full border border-border rounded-lg p-2 bg-card";

export function InvoiceFormPage() {
  const {invoiceId} = useParams(); const navigate = useNavigate();
  const [form,setForm] = useState<InvoiceInput>(empty); const [company,setCompany] = useState<Company | null>(null);
  const [customers,setCustomers] = useState<CustomerOption[]>([]); const [search,setSearch] = useState("");
  const [error,setError] = useState<string | null>(null); const [busy,setBusy] = useState(false);
  const [ready,setReady] = useState(false); const [pdf,setPdf] = useState<Blob | null>(null); const [url,setUrl] = useState("");
  useEffect(()=>{let active=true;
    Promise.all([getDefaults(),invoiceId ? getInvoice(invoiceId) : Promise.resolve(null)]).then(([defaults,invoice])=>{
      if(!active) return; setCompany(defaults);
      if(invoice) {
        if(invoice.status!=="draft") {setError("Only draft invoices can be edited.");return;}
        const data: InvoiceInput = {customer_id:invoice.customer_id,customer:invoice.customer,invoice_date:invoice.invoice_date,due_date:invoice.due_date,place_of_supply:invoice.place_of_supply,terms:invoice.terms,tax_type:invoice.tax_type,version:invoice.version,
          items:invoice.items.map(({description,hsn,quantity,unit,rate,gst_rate})=>({description,hsn,quantity,unit,rate,gst_rate}))};
        setForm(data);
      } else setForm(f=>({...f,terms:defaults.default_terms,items:[blankItem(defaults.default_gst)]}));
      setReady(true);
    }).catch(e=>{if(active) setError(getErrorMessage(e));});return()=>{active=false;};
  },[invoiceId]);
  useEffect(()=>{let active=true;const timer=setTimeout(()=>getCustomers(search).then(v=>{if(active)setCustomers(v);}).catch(e=>{if(active)setError(getErrorMessage(e));}),250);return()=>{active=false;clearTimeout(timer);};},[search]);
  useEffect(()=>{if(!pdf){setUrl("");return;}const next=URL.createObjectURL(pdf);setUrl(next);return()=>URL.revokeObjectURL(next);},[pdf]);
  const change = (next: InvoiceInput) => {setForm(next);setPdf(null);};
  const rowChange = (index: number, key: keyof Item, value: string) => change({...form,items:form.items.map((row,i)=>i===index?{...row,[key]:value}:row)});
  let totals: ReturnType<typeof calculateItems> | null = null;
  try {totals=calculateItems(form.items,form.tax_type==="CGST_SGST");} catch { /* incomplete input; backend validates on save */ }
  async function submit(preview: boolean) {
    setError(null);setBusy(true);
    try {if(preview) setPdf(await previewPdf(form)); else {const invoice=await saveInvoice(form,invoiceId);navigate(`/invoices/${invoice.id}`);}}
    catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}
  }
  return <SimplePageLayout title={invoiceId?"Edit draft invoice":"Create invoice"} backTo="/invoices">
    <ErrorBanner message={error}/>
    {!ready ? <p>{error?"Invoice unavailable.":"Loading invoice…"}</p> : <form onSubmit={e=>{e.preventDefault();void submit(false);}} className="space-y-6">
      <section className="bg-card border rounded-xl p-5"><h2 className="font-semibold mb-4">Invoice details</h2><p className="text-sm mb-4">Invoice number is assigned automatically and remains fixed after creation.</p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <label>Invoice date<input className={inputClass} type="date" required value={form.invoice_date} onChange={e=>change({...form,invoice_date:e.target.value})}/></label>
          <label>Valid until / Due date<input className={inputClass} type="date" required min={form.invoice_date} value={form.due_date} onChange={e=>change({...form,due_date:e.target.value})}/></label>
          <label>Tax structure<select className={inputClass} value={form.tax_type} onChange={e=>change({...form,tax_type:e.target.value as InvoiceInput["tax_type"]})}><option value="IGST">IGST</option><option value="CGST_SGST">CGST + SGST</option></select></label>
          <label>Place of supply<input className={inputClass} maxLength={100} value={form.place_of_supply} onChange={e=>change({...form,place_of_supply:e.target.value})}/></label>
        </div>
      </section>
      <section className="bg-card border rounded-xl p-5"><h2 className="font-semibold mb-4">Customer details</h2>
        <div className="grid sm:grid-cols-2 gap-4 mb-4"><label>Find existing customer<input className={inputClass} placeholder="Search customer name" value={search} onChange={e=>setSearch(e.target.value)}/></label>
          <label>Customer<select className={inputClass} value={form.customer_id??""} onChange={e=>{
            const selected=customers.find(c=>c.id===e.target.value);
            if(!selected){change({...form,customer_id:null});return;}
            change({...form,customer_id:selected.id,customer:{name:selected.name,phone:selected.phone,email:selected.email,gstin:"",address:[selected.address.line1,selected.address.line2].filter(Boolean).join(", "),city:selected.address.city??"",state:selected.address.state??"",pincode:selected.address.pincode??"",country:selected.address.country??"India"}});
          }}><option value="">Manual company / billing recipient</option>{form.customer_id && !customers.some(c=>c.id===form.customer_id) && <option value={form.customer_id}>{form.customer.name}</option>}{customers.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{(Object.keys(form.customer) as (keyof typeof form.customer)[]).map(key=><label key={key} className={key==="address"?"sm:col-span-2":""}>{({name:"Customer / Company name",address:"Address",city:"City",state:"State",pincode:"PIN Code",country:"Country",gstin:"GSTIN",phone:"Phone",email:"Email"})[key]}
          <input className={inputClass} required={key==="name"||key==="address"} type={key==="email"?"email":"text"} maxLength={key==="address"?500:key==="gstin"?15:150} pattern={key==="gstin"?"[0-9]{2}[A-Z0-9]{13}":key==="pincode"?"[0-9]{6}":undefined} value={form.customer[key]} onChange={e=>change({...form,customer:{...form.customer,[key]:key==="gstin"?e.target.value.toUpperCase():e.target.value}})}/>
        </label>)}</div>
      </section>
      <section className="bg-card border rounded-xl p-5"><h2 className="font-semibold mb-4">Invoice items</h2><div className="overflow-x-auto"><table className="w-full text-sm min-w-[1100px]"><thead><tr>{["No.","Item & Description","HSN/SAC","Qty","Unit","Rate (₹)","Taxable","GST %","GST","Total","Actions"].map(v=><th className="p-2 text-left" key={v}>{v}</th>)}</tr></thead>
        <tbody>{form.items.map((row,index)=><tr key={index}><td>{index+1}</td>{(Object.keys(row) as (keyof Item)[]).filter(key=>key!=="gst_rate").map(key=><td className="p-1" key={key}>
          {key==="description"?<textarea aria-label={`Item ${index+1} description`} className={inputClass+" min-w-48"} required maxLength={500} value={row[key]} onChange={e=>rowChange(index,key,e.target.value)}/>:
          <input aria-label={`Item ${index+1} ${key}`} className={inputClass+" min-w-20"} required type={["quantity","rate"].includes(key)?"number":"text"} min={key==="quantity"?"0.001":key==="rate"?"0":undefined} step={key==="quantity"?"0.001":"0.01"} pattern={key==="hsn"?"[0-9]{4,8}":undefined} value={row[key]} onChange={e=>rowChange(index,key,e.target.value)}/>}</td>)}
          <td>{totals?money(totals.rows[index].taxable):"—"}</td><td><input aria-label={`Item ${index+1} GST %`} className={inputClass+" min-w-20"} required type="number" min="0" max="100" step="0.01" value={row.gst_rate} onChange={e=>rowChange(index,"gst_rate",e.target.value)}/></td>
          <td>{totals?money(totals.rows[index].gst):"—"}</td><td>{totals?money(totals.rows[index].total):"—"}</td><td><Button variant="ghost" disabled={form.items.length===1} onClick={()=>change({...form,items:form.items.filter((_,i)=>i!==index)})}>Remove</Button>
          <Button variant="ghost" aria-label={`Move item ${index+1} up`} disabled={index===0} onClick={()=>{const items=[...form.items];[items[index-1],items[index]]=[items[index],items[index-1]];change({...form,items});}}>↑</Button></td></tr>)}</tbody></table></div>
        <Button variant="secondary" className="mt-3" disabled={form.items.length>=100} onClick={()=>change({...form,items:[...form.items,blankItem(company?.default_gst)]})}>+ Add item</Button>
      </section>
      <div className="grid lg:grid-cols-2 gap-5"><section className="bg-card border rounded-xl p-5"><h2 className="font-semibold mb-3">Bank details preview</h2><p>{company?.bank_name || "Configure bank details in Invoice Settings before issuing."}</p><p>Branch: {company?.branch}</p><p>Account: {company?.account_number}</p><p>IFSC: {company?.ifsc}</p><label className="block mt-4">Payment terms<textarea className={inputClass} maxLength={500} value={form.terms} onChange={e=>change({...form,terms:e.target.value})}/></label></section>
        <section className="bg-card border rounded-xl p-5"><h2 className="font-semibold mb-3">Tax & totals</h2><p>Subtotal: {totals?money(totals.subtotal):"—"}</p><p>{form.tax_type==="IGST"?"IGST":"CGST + SGST"}: {totals?money(totals.gst):"—"}</p><p className="font-semibold text-xl mt-3">Grand total: {totals?money(totals.total):"—"}</p><p className="text-sm mt-3">Final totals and amount in words are validated by the server when saved.</p></section></div>
      <div className="flex gap-3"><Button variant="secondary" loading={busy} onClick={e=>{if(e.currentTarget.form?.reportValidity()) void submit(true);}}>Preview invoice</Button><Button type="submit" loading={busy}>Save draft</Button></div>
      {url && <section><h2 className="font-semibold mb-3">Invoice preview</h2><iframe title="Invoice preview" src={url} className="w-full h-[900px] border rounded-xl"/></section>}
    </form>}
  </SimplePageLayout>;
}
