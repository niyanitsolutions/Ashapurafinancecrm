import { useId, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { usePermissions } from "@/features/access_control/usePermissions";
import { formatISTDate } from "@/shared/dateFormat";
import { archiveInterestOption, createInterestOption, renameInterestOption, useInterestOptions, type InterestOption } from "./interestOptions";

export function CustomerInterestField({value,onChange,historicalId,historicalLabel}: {value:string;onChange:(id:string)=>void;historicalId?:string;historicalLabel?:string}) {
  const options=useInterestOptions(); const cache=useQueryClient(); const {can}=usePermissions();
  const manageAllowed=can("daily_operations:follow-ups","create")||can("daily_operations:follow-ups","edit");
  const [open,setOpen]=useState(false);const [search,setSearch]=useState("");const [manage,setManage]=useState(false);
  const [editing,setEditing]=useState<InterestOption|null|undefined>(undefined);const [name,setName]=useState("");
  const [removing,setRemoving]=useState<InterestOption|null>(null);const [busy,setBusy]=useState(false);const lock=useRef(false);
  const [error,setError]=useState<string|null>(null);const [notice,setNotice]=useState("");const id=useId();
  const rows=options.data??[];const selected=rows.find(row=>row.id===value);
  const label=value&&value===historicalId?historicalLabel:selected?.name;
  async function mutate(action:()=>Promise<InterestOption>,created=false) {
    if(lock.current)return;lock.current=true;setBusy(true);setError(null);setNotice("");
    try{const row=await action();await cache.invalidateQueries({queryKey:["daily-interest-options"]});if(created)onChange(row.id);setEditing(undefined);setRemoving(null);setNotice("Option saved.");}
    catch(e){setError(e instanceof Error?e.message:"Unable to save option.");await options.refetch();}
    finally{lock.current=false;setBusy(false);}
  }
  function edit(row:InterestOption|null){setEditing(row);setName(row?.name??search);setError(null);}
  return <section className="mb-4 min-w-0">
    <label htmlFor={id} className="mb-1.5 block text-sm font-medium">Customer Interest Status</label>
    <Button id={id} variant="secondary" className="w-full justify-between" aria-expanded={open} aria-controls={`${id}-options`} onClick={()=>{setOpen(!open);if(!open)void options.refetch();}}>{label||"Select interest status (optional)"}{selected&&!selected.is_active?" (archived)":""}<span aria-hidden="true"> &#9662;</span></Button>
    {open&&<div id={`${id}-options`} className="mt-2 rounded-lg border border-border bg-card p-3 space-y-2" onKeyDown={event=>{if(event.key==="Escape"){setOpen(false);event.stopPropagation();}if(event.key==="Enter"&&event.target instanceof HTMLInputElement)event.preventDefault();}}>
      <FormField label="Search interest options" value={search} onChange={event=>setSearch(event.target.value)} />
      {options.isLoading&&<p role="status">Loading options...</p>}
      {options.isError&&<><ErrorBanner message="Unable to load interest options."/><Button variant="secondary" onClick={()=>void options.refetch()}>Retry options</Button></>}
      {!options.isLoading&&!options.isError&&<>
        <label htmlFor={`${id}-select`} className="text-sm">Available interest options</label>
        <select id={`${id}-select`} className="block w-full rounded-lg border border-border bg-card p-2" size={5} value={value} onChange={event=>{onChange(event.target.value);setOpen(false);}}>
          <option value="">No interest status</option>
          {value&&value===historicalId&&<option value={value}>{historicalLabel||"Saved historical value"} (saved{selected&&!selected.is_active?", archived":""})</option>}
          {rows.filter(row=>row.is_active&&!(value===historicalId&&row.id===historicalId)&&row.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map(row=><option key={row.id} value={row.id}>{row.name}</option>)}
        </select>
        {!rows.some(row=>row.is_active)&&<p>No saved options. Add your first custom option.</p>}
        {!!search&&!rows.some(row=>row.is_active&&row.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()))&&<p>No matching options.</p>}
      </>}
      {manageAllowed&&<div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={()=>edit(null)}>Add Custom Option</Button><Button variant="secondary" onClick={()=>setManage(!manage)}>Manage Options</Button></div>}
      <ErrorBanner message={error}/>{notice&&<p role="status">{notice}</p>}
      {editing!==undefined&&<div className="rounded-lg border border-border p-3"><FormField label="Option name" required maxLength={60} value={name} onChange={event=>setName(event.target.value)}/><div className="flex gap-2"><Button disabled={busy||!name.trim()} onClick={()=>void mutate(()=>editing?renameInterestOption(editing,name):createInterestOption(name),editing===null)}>Save option</Button><Button variant="secondary" disabled={busy} onClick={()=>setEditing(undefined)}>Cancel option edit</Button></div></div>}
      {manage&&manageAllowed&&<div className="space-y-2"><h3 className="font-medium">Manage interest options</h3>{rows.map(row=><div key={row.id} className="rounded-lg border border-border p-3 text-sm break-words"><p className="font-medium">{row.name}{!row.is_active?" (archived)":""}</p><p>Created by: {row.created_by_name} &middot; {formatISTDate(row.created_at)}</p><p>Updated: {formatISTDate(row.updated_at)}</p><div className="mt-2 flex flex-wrap gap-2"><Button size="sm" variant="secondary" disabled={busy} onClick={()=>edit(row)}>Edit {row.name}</Button>{row.is_active?<Button size="sm" variant="danger" disabled={busy} onClick={()=>setRemoving(row)}>Remove {row.name}</Button>:<Button size="sm" variant="secondary" disabled={busy} onClick={()=>void mutate(()=>archiveInterestOption(row,true))}>Restore {row.name}</Button>}</div></div>)}</div>}
      <Button variant="ghost" onClick={()=>void options.refetch()}>Refresh options</Button>
    </div>}
    <ConfirmDialog open={!!removing} title="Remove interest option?" message="This hides the option from new selections. Existing records keep their saved value. You can restore it in Manage Options." confirmLabel="Remove option" confirmVariant="danger" onClose={()=>setRemoving(null)} onConfirm={async()=>{if(removing)await mutate(()=>archiveInterestOption(removing));}}/>
  </section>;
}
