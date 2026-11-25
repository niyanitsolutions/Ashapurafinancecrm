import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { ProductSchemaForm, RepeatableGroupsForm } from "@/components/forms/ProductSchemaForm";
import { isFieldVisible, validateFormData } from "@/components/forms/fieldValidation";
import { usePermissions } from "@/features/access_control/usePermissions";
import { ApiError } from "@/shared/api/client";
import { updateSubmittedApplication, type ApplicationDetail, type FormDefinition } from "../api";
export function SubmittedApplicationDetails({application,schema,onSaved}: {application:ApplicationDetail;schema:FormDefinition | null;onSaved:(app:ApplicationDetail)=>void}) {
  const {can}=usePermissions();
  const [editing,setEditing]=useState(false);
  const [values,setValues]=useState<Record<string,unknown>>({});
  const [reason,setReason]=useState("");
  const [busy,setBusy]=useState(false);
  const lock=useRef(false);
  const [error,setError]=useState<string | null>(null);
  const [errors,setErrors]=useState<Record<string,string>>({});
  const [success,setSuccess]=useState(false);
  const change=(key:string,value:unknown)=>setValues(previous=>({...previous,[key]:value}));
  const editableKeys=new Set([...(schema?.fields || []).filter(f=>isFieldVisible(f,values)).map(f=>f.key),...(schema?.repeatable_groups || []).map(g=>g.key)]);
  const readOnlyKeys=Object.keys(application.form_data).filter(key=>!editableKeys.has(key));
  const labels=Object.fromEntries((schema?.fields || []).map(f=>[f.key,f.label]));
  return <section className="rounded-card border border-border bg-card p-4 sm:p-6">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="text-sm font-semibold">Application Details</h2>
      {!editing && can("customer:customers","edit") && <Button size="sm" variant="secondary" disabled={!schema} onClick={()=>{setValues(JSON.parse(JSON.stringify(application.form_data)));setReason("");setError(null);setErrors({});setSuccess(false);setEditing(true);}}>Edit Details</Button>}
    </div>
    <p className="mb-2 text-sm">Application ID: {application.application_code}</p>
    {application.customer_id && <Link className="mb-3 inline-block text-xs text-primary hover:underline" to={`/customers/${application.customer_id}`}>View shared customer identity</Link>}
    <ErrorBanner message={error}/>{success && <p role="status" className="mb-3 text-sm text-success">Application details saved.</p>}
    {editing && schema ? <form noValidate onSubmit={async event=>{
      event.preventDefault();if(lock.current)return;
      const validation=validateFormData(schema.fields,values);setErrors(validation);if(Object.keys(validation).length)return;
      lock.current=true;setBusy(true);setError(null);
      try {
        const allowed=new Set([...schema.fields.filter(f=>isFieldVisible(f,values)).map(f=>f.key),...(schema.repeatable_groups || []).map(g=>g.key)]);
        const patch=Object.fromEntries(Object.entries(values).filter(([key,value])=>allowed.has(key)&&JSON.stringify(value)!==JSON.stringify(application.form_data[key])));
        const saved=await updateSubmittedApplication(application.id,patch,application.version || 1,reason);
        onSaved(saved);setEditing(false);setValues({});setSuccess(true);
      } catch(e) {
        if(e instanceof ApiError && e.details && typeof e.details === "object" && "field_errors" in e.details) setErrors((e.details as {field_errors:Record<string,string>}).field_errors);
        setError(e instanceof ApiError ? e.message : "Unable to save application details.");
      } finally {lock.current=false;setBusy(false);}
    }}>
      <p className="mb-4 text-xs text-textSecondary">These are this application's submitted answers. Shared identity changes use the existing Customer profile workflow; other applications remain unchanged.</p>
      <fieldset disabled={busy}><ProductSchemaForm fields={schema.fields} values={values} onChange={change} errors={errors}/><RepeatableGroupsForm groups={schema.repeatable_groups || []} values={values} onChange={change} errors={errors}/>
      {readOnlyKeys.length>0 && <section className="mb-4 rounded-lg border border-border p-3"><h3 className="mb-2 text-sm font-medium">Read-only historical answers</h3><dl className="space-y-2 text-sm">{readOnlyKeys.map(key=><div key={key}><dt className="text-xs text-textSecondary">{labels[key] || key.replaceAll("_"," ")}</dt><dd className="break-words">{String(application.form_data[key] ?? "Not provided")}</dd></div>)}</dl></section>}
      <FormField label="Reason for correction" required minLength={3} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <div className="flex gap-3"><Button type="submit" loading={busy} disabled={reason.trim().length<3}>Save Changes</Button><Button variant="secondary" disabled={busy} onClick={()=>{setEditing(false);setValues({});setErrors({});setError(null);}}>Cancel</Button></div></fieldset>
    </form> : <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">{Object.entries(application.form_data).map(([key,value])=><div key={key}><dt className="text-xs capitalize text-textSecondary">{labels[key] || key.replaceAll("_"," ")}</dt><dd className="break-words">{Array.isArray(value) ? value.map((block,index)=><div key={index} className="my-1">{typeof block === "object" && block ? Object.entries(block).map(([k,v])=>`${k.replaceAll("_"," ")}: ${v}`).join("; ") : String(block)}</div>) : String(value ?? "Not provided")}</dd></div>)}</dl>}
  </section>;
}
