import { useId, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { usePermissions } from "@/features/access_control/usePermissions";
import { archiveBankOption,createBankOption,editBankOption,useBankOptions,type BankOption,type BankSelection } from "./bankOptions";

export function BankMultiSelect({value,onChange}:{value:BankSelection[];onChange:(banks:BankSelection[])=>void}){
 const options=useBankOptions();const cache=useQueryClient();const {can}=usePermissions();const id=useId();
 const allowed=can("daily_operations:follow-ups","create")||can("daily_operations:follow-ups","edit");
 const [open,setOpen]=useState(false);const [search,setSearch]=useState("");const [manage,setManage]=useState(false);const [editing,setEditing]=useState<BankOption|null|undefined>();const [name,setName]=useState("");const [removing,setRemoving]=useState<BankOption|null>(null);const [error,setError]=useState<string|null>(null);const [notice,setNotice]=useState("");const [busy,setBusy]=useState(false);const lock=useRef(false);
 const rows=options.data??[];const matching=rows.filter(row=>(manage||row.is_active)&&row.name.toLowerCase().includes(search.toLowerCase()));
 async function mutate(action:()=>Promise<BankOption>,created=false){if(lock.current)return;lock.current=true;setBusy(true);setError(null);try{const row=await action();cache.setQueriesData<BankOption[]>({queryKey:["daily-bank-options"]},old=>old?[...old.filter(item=>item.id!==row.id),row]:[row]);if(created&&!value.some(item=>item.option_id===row.id))onChange([...value,{option_id:row.id,name:row.name}]);setEditing(undefined);setRemoving(null);setNotice("Bank / NBFC option saved.");await cache.invalidateQueries({queryKey:["daily-bank-options"]});}catch(e){setError(e instanceof Error?e.message:"Unable to save bank option.");await options.refetch();}finally{lock.current=false;setBusy(false);}}
 function edit(row:BankOption|null){setEditing(row);setName(row?.name??search);setError(null);}
 return <section className="mb-4 min-w-0">
  <label htmlFor={id} className="mb-1.5 block text-sm font-medium">Bank / NBFC</label>
  <div className="mb-2 flex flex-wrap gap-1" aria-label="Selected banks">{value.map((bank,index)=><span key={bank.option_id??bank.name} className="inline-flex max-w-full items-center gap-1 rounded-lg bg-primary/10 px-2 py-1 text-sm"><span className="break-words">{bank.name}</span><button type="button" className="min-h-8 min-w-8 rounded focus-visible:outline focus-visible:outline-primary" aria-label={`Remove selected bank ${bank.name}`} disabled={busy} onClick={()=>onChange(value.filter((_,i)=>i!==index))}>&times;</button></span>)}</div>
  <Button id={id} variant="secondary" className="w-full justify-between" aria-expanded={open} aria-controls={`${id}-banks`} onClick={()=>{setOpen(!open);if(!open)void options.refetch();}}>{value.length?`${value.length} bank${value.length===1?"":"s"} selected`:"Select banks / NBFCs"}<span aria-hidden="true">&#9662;</span></Button>
  {open&&<div id={`${id}-banks`} className="mt-2 space-y-2 rounded-lg border border-border bg-card p-3" onKeyDown={event=>{if(event.key==="Escape"){setOpen(false);event.stopPropagation();}if(event.key==="Enter"&&event.target instanceof HTMLInputElement&&event.target.type!=="checkbox")event.preventDefault();}}>
   <FormField label="Search banks / NBFCs" value={search} onChange={event=>setSearch(event.target.value)}/>
   {options.isLoading&&<p role="status">Loading bank options...</p>}{options.isError&&<><ErrorBanner message="Unable to load bank options."/><Button variant="secondary" onClick={()=>void options.refetch()}>Retry bank options</Button></>}
   <div className="max-h-52 overflow-y-auto space-y-1" role="group" aria-label="Available banks / NBFCs">{matching.map(row=><div key={row.id} className="rounded-lg border border-border p-2"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.some(item=>item.option_id===row.id)} disabled={busy||!row.is_active||(!value.some(item=>item.option_id===row.id)&&value.length>=30)} onChange={event=>onChange(event.target.checked?[...value,{option_id:row.id,name:row.name}]:value.filter(item=>item.option_id!==row.id))}/><span className="break-words">{row.name}{!row.is_active?" (archived)":""}</span></label>{manage&&allowed&&<div className="mt-2 flex flex-wrap gap-2"><Button size="sm" variant="secondary" disabled={busy} onClick={()=>edit(row)}>Edit {row.name}</Button>{row.is_active?<Button size="sm" variant="danger" disabled={busy} onClick={()=>setRemoving(row)}>Archive {row.name}</Button>:<Button size="sm" variant="secondary" disabled={busy} onClick={()=>void mutate(()=>archiveBankOption(row,true))}>Restore {row.name}</Button>}</div>}</div>)}</div>
   {!options.isLoading&&!options.isError&&!matching.length&&<p>No matching banks / NBFCs. Add a custom bank to continue.</p>}
   {allowed&&<div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" disabled={busy||value.length>=30} onClick={()=>edit(null)}>Add Custom Bank / NBFC</Button><Button size="sm" variant="secondary" aria-expanded={manage} onClick={()=>setManage(!manage)}>Manage Bank Options</Button></div>}
   <ErrorBanner message={error}/>{notice&&<p role="status">{notice}</p>}
   {editing!==undefined&&<div className="rounded-lg border border-border p-3"><FormField label="Bank / NBFC name" value={name} maxLength={200} onChange={event=>setName(event.target.value)}/><div className="flex flex-wrap gap-2"><Button disabled={busy||!name.trim()} onClick={()=>void mutate(()=>editing?editBankOption(editing,name):createBankOption(name),editing===null)}>Save bank option</Button><Button variant="secondary" disabled={busy} onClick={()=>setEditing(undefined)}>Cancel bank edit</Button></div></div>}
   <Button variant="ghost" onClick={()=>void options.refetch()}>Refresh bank options</Button>
  </div>}
  <ConfirmDialog open={!!removing} title="Archive Bank / NBFC?" message="Existing daily records keep their saved bank. The option will be hidden from new selections and can be restored." confirmLabel="Archive bank" confirmVariant="danger" onClose={()=>setRemoving(null)} onConfirm={async()=>{if(removing)await mutate(()=>archiveBankOption(removing));}}/>
 </section>;
}
