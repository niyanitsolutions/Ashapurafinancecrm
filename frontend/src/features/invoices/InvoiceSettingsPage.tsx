import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/shared/api/errors";
import { ApiError } from "@/shared/api/client";
import { confirmLogo, getLogoUploadUrl } from "@/features/system_settings/api";
import { getSettings, saveSettings, uploadSignature, type InvoiceConfig } from "./api";

const fields: {title: string; keys: [keyof InvoiceConfig,string][]}[] = [
  {title:"Company invoice information",keys:[["gstin","Company GSTIN"],["website","Website"]]},
  {title:"Bank details",keys:[["bank_name","Bank name"],["branch","Branch"],["account_holder","Account holder"],["account_number","Account number"],["ifsc","IFSC"]]},
  {title:"Invoice numbering & defaults",keys:[["prefix","Invoice prefix"],["starting_number","Starting number (minimum for future allocation)"],["default_gst","Default GST %"],["default_terms","Default payment terms"]]},
  {title:"Authorized signature",keys:[["signatory","Signatory name"],["designation","Designation"]]},
];
export function InvoiceSettingsPage() {
  const [config,setConfig]=useState<InvoiceConfig | null>(null);const [error,setError]=useState<string | null>(null);
  const [saved,setSaved]=useState(false);const [busy,setBusy]=useState(false);const [signature,setSignature]=useState<string | null>(null);
  const [logo,setLogo]=useState<string | null>(null);const [company,setCompany]=useState("");
  useEffect(()=>{let active=true;getSettings().then(s=>{if(active){setConfig(s.config);setSignature(s.assets.signature);setLogo(s.assets.logo);setCompany(s.company.name);}}).catch(e=>{if(active)setError(getErrorMessage(e));});return()=>{active=false;};},[]);
  return <SimplePageLayout title="Invoice settings" backTo="/settings" subtitle="Company, bank, numbering, signature and QR configuration">
    <ErrorBanner message={error}/>{saved&&<p role="status" className="mb-4 text-success">Invoice settings saved.</p>}
    {config&&<form className="space-y-5" onSubmit={async e=>{e.preventDefault();setBusy(true);setError(null);setSaved(false);try{setConfig(await saveSettings(config));setSaved(true);}catch(err){setError(getErrorMessage(err));}finally{setBusy(false);}}}>
      <section className="border rounded-xl bg-card p-5"><h2 className="font-semibold">{company}</h2><p className="mt-2">Company name, address and contact details use the existing <Link className="text-primary" to="/settings/company">Company Settings</Link>.</p>{logo&&<img className="h-24 object-contain mt-3" src={logo} alt="Company logo"/>}
        <label className="block mt-3">Upload or replace company logo (PNG, up to 5 MB)<input className="block mt-2" type="file" accept="image/png" disabled={busy} onChange={async e=>{
          const file=e.target.files?.[0];if(!file)return;setBusy(true);setError(null);
          try {
            if(file.type!=="image/png"||file.size>5*1024*1024)throw new ApiError("validation_error","Choose a PNG logo up to 5 MB.");
            const upload=await getLogoUploadUrl();
            const response=await fetch(upload.upload_url,{method:"PUT",body:file,headers:{"Content-Type":"image/png"}});
            if(!response.ok)throw new ApiError("upload_error","Logo upload failed. Please try again.");
            await confirmLogo(upload.s3_key);setLogo((await getSettings()).assets.logo);
          } catch(err){setError(getErrorMessage(err));}finally{setBusy(false);}
        }}/></label>
      </section>
      {fields.map(section=><section className="border rounded-xl bg-card p-5" key={section.title}><h2 className="font-semibold mb-4">{section.title}</h2><div className="grid sm:grid-cols-2 gap-4">{section.keys.map(([key,label])=><label key={key}>{label}<input className="block w-full border rounded-lg p-2 mt-1" value={String(config[key]??"")} type={key==="starting_number"||key==="default_gst"?"number":"text"} min={key==="starting_number"?1:0} max={key==="default_gst"?100:undefined} step={key==="default_gst"?"0.01":1} onChange={e=>{setSaved(false);setConfig({...config,[key]:key==="starting_number"?Number(e.target.value):e.target.value});}}/></label>)}</div></section>)}
      <section className="border rounded-xl bg-card p-5"><h2 className="font-semibold mb-3">Signature image</h2><label className="block mb-3"><input type="checkbox" checked={config.show_signature} onChange={e=>setConfig({...config,show_signature:e.target.checked})}/> Display signature on invoices</label>
        {signature&&<img src={signature} className="h-24 object-contain mb-3" alt="Authorized signature preview"/>}
        <label>Upload or replace signature (PNG, up to 2 MB)<input className="block mt-2" type="file" accept="image/png" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;setBusy(true);setError(null);try{const result=await uploadSignature(file);setConfig({...config,signature_s3_key:result.s3_key});setSignature(result.preview_url);setSaved(false);}catch(err){setError(getErrorMessage(err));}finally{setBusy(false);}}}/></label>
        <Button variant="ghost" onClick={()=>{setConfig({...config,signature_s3_key:null});setSignature(null);}}>Remove signature</Button>
      </section>
      <section className="border rounded-xl bg-card p-5"><h2 className="font-semibold mb-3">QR code</h2><label>QR type<select className="block border rounded-lg p-2 mt-1" value={config.qr_type} onChange={e=>setConfig({...config,qr_type:e.target.value as InvoiceConfig["qr_type"]})}><option value="none">Disabled</option><option value="identifier">Invoice identifier</option><option value="upi">UPI payment</option></select></label>
        {config.qr_type==="upi"&&<label className="block mt-3">UPI ID<input className="block border rounded-lg p-2 mt-1" required value={config.upi_id} onChange={e=>setConfig({...config,upi_id:e.target.value})}/></label>}
        <p className="text-sm mt-3">QR values are generated by the server when an invoice is issued. Invoice identifiers are informational; UPI QR codes use the configured account and stored invoice total.</p>
      </section><Button type="submit" loading={busy}>Save invoice settings</Button>
    </form>}
  </SimplePageLayout>;
}
