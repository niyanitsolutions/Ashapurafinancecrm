import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { usePermissions } from "@/features/access_control/usePermissions";
import { contrastText, archiveStatusOption, createStatusOption, updateStatusOption, useStatusOptions, type StatusOption } from "./statusOptions";

const presets=["#FFF0C2","#DCEBFF","#D9F5E3","#FFE0E0","#EDE3FF","#FFE6CC","#D9F2F2","#E5E7EB"];
export function FollowUpStatusField({value,onChange,historicalValue,historicalLabel}: {value:string;onChange:(value:string)=>void;historicalValue?:string;historicalLabel?:string}) {
  const options=useStatusOptions();const cache=useQueryClient();const {can}=usePermissions();
  const allowed=can("daily_operations:follow-ups","create")||can("daily_operations:follow-ups","edit");
  const [manage,setManage]=useState(false);const [search,setSearch]=useState("");
  const [editing,setEditing]=useState<StatusOption|null|undefined>();const [name,setName]=useState("");const [color,setColor]=useState(presets[0]);const [order,setOrder]=useState(100);
  const [removing,setRemoving]=useState<StatusOption|null>(null);const [error,setError]=useState<string|null>(null);const [notice,setNotice]=useState("");const [busy,setBusy]=useState(false);const lock=useRef(false);
  const rows=options.data??[];const validColor=/^#[0-9A-Fa-f]{6}$/.test(color);
  const available=rows.filter(row=>row.is_active).map(row=>({value:row.value,label:row.name}));
  if(historicalValue&&!available.some(row=>row.value===historicalValue))available.push({value:historicalValue,label:`${historicalLabel||historicalValue} (saved, archived)`});
  async function mutate(action:()=>Promise<StatusOption>,created=false){
    if(lock.current)return;lock.current=true;setBusy(true);setError(null);setNotice("");
    try{const row=await action();cache.setQueriesData<StatusOption[]>({queryKey:["daily-follow-up-status-options"]},old=>old?[...old.filter(item=>item.id!==row.id),row].sort((a,b)=>a.display_order-b.display_order):[row]);if(created)onChange(row.value);setEditing(undefined);setRemoving(null);setNotice("Status option saved.");await cache.invalidateQueries({queryKey:["daily-follow-up-status-options"]});}
    catch(e){setError(e instanceof Error?e.message:"Unable to save status option.");await options.refetch();}
    finally{lock.current=false;setBusy(false);}
  }
  function edit(row:StatusOption|null){setEditing(row);setName(row?.name??"");setColor(row?.color??presets[0]);setOrder(row?.display_order??100);setError(null);}
  return <section className="mb-4 min-w-0">
    <SelectField label="Follow-up status" required value={value} options={available} onChange={event=>onChange(event.target.value)}/>
    {options.isLoading&&<p role="status" className="text-sm">Loading status options...</p>}
    {options.isError&&<><ErrorBanner message="Unable to load Follow-up Status options."/><Button variant="secondary" onClick={()=>void options.refetch()}>Retry status options</Button></>}
    {allowed&&<div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={()=>edit(null)}>Add Custom Option</Button><Button size="sm" variant="secondary" aria-expanded={manage} onClick={()=>{setManage(!manage);void options.refetch();}}>Manage Options</Button></div>}
    <ErrorBanner message={error}/>{notice&&<p role="status" className="mt-2 text-sm">{notice}</p>}
    {editing!==undefined&&<div className="mt-3 rounded-xl border border-border p-3" onKeyDown={event=>{if(event.key==="Enter"&&event.target instanceof HTMLInputElement)event.preventDefault();}}>
      <h3 className="mb-3 font-medium">{editing?"Edit Follow-up Status":"Add Follow-up Status"}</h3>
      <FormField label="Status name" maxLength={60} disabled={Boolean(editing?.is_system)} value={name} onChange={event=>setName(event.target.value)}/>
      {editing?.is_system&&<p className="mb-3 text-sm text-textSecondary">Default status names are kept so their existing workflow rules continue to apply.</p>}
      <div className="grid grid-cols-[auto_1fr] gap-3"><FormField label="Color picker" type="color" value={validColor?color:"#FFFFFF"} onChange={event=>setColor(event.target.value.toUpperCase())}/><FormField label="Custom HEX color" value={color} maxLength={7} error={validColor?undefined:"Use a six-digit HEX color, for example #FFF0C2."} onChange={event=>setColor(event.target.value.toUpperCase())}/></div>
      <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Preset status colors">{presets.map(preset=><button type="button" key={preset} aria-label={`Use color ${preset}`} aria-pressed={color===preset} className="h-9 w-9 rounded-lg border border-black/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary" style={{backgroundColor:preset}} onClick={()=>setColor(preset)}/>)}</div>
      <FormField label="Display order" type="number" min={0} max={100000} value={order} onChange={event=>setOrder(Number(event.target.value))}/>
      {validColor&&<div className="mb-3 rounded-lg px-3 py-3" style={{backgroundColor:color,color:contrastText(color)}} aria-label="Status color preview">{name||"Status preview"}</div>}
      <div className="flex flex-wrap gap-2"><Button disabled={busy||!name.trim()||!validColor||!Number.isInteger(order)||order<0||order>100000} onClick={()=>void mutate(()=>editing?updateStatusOption(editing,name,color,order):createStatusOption(name,color,order),editing===null)}>Save status option</Button><Button variant="secondary" disabled={busy} onClick={()=>setEditing(undefined)}>Cancel status edit</Button></div>
    </div>}
    {manage&&allowed&&<div className="mt-3 rounded-xl border border-border p-3"><h3 className="mb-3 font-medium">Manage Follow-up Status Options</h3><FormField label="Search status options" value={search} onChange={event=>setSearch(event.target.value)}/><div className="space-y-2">{rows.filter(row=>row.name.toLowerCase().includes(search.toLowerCase())).map(row=><div key={row.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-border p-2"><div className="min-w-0 flex-1 rounded-lg p-3 text-sm font-medium break-words" style={{backgroundColor:row.color,color:contrastText(row.color)}}>{row.name}{!row.is_active?" (archived)":""}</div><Button size="sm" variant="secondary" disabled={busy} aria-label={`Edit color and name for ${row.name}`} onClick={()=>edit(row)}>Edit / Color</Button>{!row.is_system&&(row.is_active?<Button size="sm" variant="danger" disabled={busy} onClick={()=>setRemoving(row)}>Archive {row.name}</Button>:<Button size="sm" variant="secondary" disabled={busy} onClick={()=>void mutate(()=>archiveStatusOption(row,true))}>Restore {row.name}</Button>)}</div>)}</div>{!rows.length&&<p>No saved status options.</p>}<Button className="mt-3 w-full" variant="secondary" onClick={()=>edit(null)}>+ Add Custom Option</Button></div>}
    <ConfirmDialog open={!!removing} title="Archive Follow-up Status?" message="This hides the status from new selections. Existing records keep their saved status and configured color. You can restore it later." confirmLabel="Archive status" confirmVariant="danger" onClose={()=>setRemoving(null)} onConfirm={async()=>{if(removing)await mutate(()=>archiveStatusOption(removing));}}/>
  </section>;
}
