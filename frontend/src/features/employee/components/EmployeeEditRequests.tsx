import {useCallback,useEffect,useState} from "react";
import {Button} from "@/components/buttons/Button";
import {FormField} from "@/components/forms/FormField";
import {ErrorBanner} from "@/components/forms/ErrorBanner";
import {ConfirmDialog} from "@/components/overlays/ConfirmDialog";
import {useAuth} from "@/features/auth/useAuth";
import {apiRequest} from "@/shared/api/client";
import {getErrorMessage} from "@/shared/api/errors";
import {hrPath} from "../hrApi";
interface Edit {id:string;status:string;requested_at:string;reason?:string;previous_values:Record<string,unknown>;proposed_values:Record<string,unknown>;reviewed_at?:string}
function display(value:unknown):string {if(value==null)return "Not applicable";if(typeof value==="object")return Object.values(value).filter(item=>item!=null&&item!=="").map(String).join(", ");return String(value);}
export function EmployeeEditRequests({employeeId,onChanged}:{employeeId:string;onChanged:()=>void}){
 const {role}=useAuth();const [rows,setRows]=useState<Edit[]>([]);const [error,setError]=useState<string|null>(null);const [review,setReview]=useState<{row:Edit;decision:string}|null>(null);const [reason,setReason]=useState("");const [busy,setBusy]=useState(false);
 const load=useCallback(async()=>{try{setRows((await apiRequest<{items:Edit[]}>(hrPath(employeeId)+"/edit-requests?page_size=200")).items);}catch(e){setError(getErrorMessage(e));}},[employeeId]);useEffect(()=>{void load();},[load]);
 async function decide(){if(!review||busy)return;setBusy(true);setError(null);try{await apiRequest(hrPath(employeeId)+`/edit-requests/${review.row.id}/review`,{method:"POST",body:JSON.stringify({decision:review.decision,reason})});setReview(null);await load();onChanged();}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}}
 return <section className="my-6"><h2 className="text-lg font-semibold">Employee edit requests</h2><ErrorBanner message={error}/>{!rows.length&&<p>No edit requests.</p>}{rows.map(row=><article key={row.id} className="my-3 rounded-lg border border-border p-4"><h3 className="font-semibold">{row.status} ? {row.requested_at}</h3>{row.reason&&<p>{row.reason}</p>}<div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr><th>Field</th><th>Official value when requested</th><th>Proposed value</th></tr></thead><tbody>{Object.entries(row.proposed_values).filter(([key,value])=>JSON.stringify(value)!==JSON.stringify(row.previous_values[key])).map(([key,value])=><tr key={key}><td className="p-2">{key.replaceAll("_"," ")}</td><td className="p-2">{display(row.previous_values[key])}</td><td className="p-2">{display(value)}</td></tr>)}</tbody></table></div>{role==="owner"&&row.status==="pending"&&<div className="flex gap-2"><Button disabled={busy} onClick={()=>{setReason("");setReview({row,decision:"approved"});}}>Approve edit request</Button><Button variant="danger" disabled={busy} onClick={()=>{setReason("");setReview({row,decision:"rejected"});}}>Reject edit request</Button></div>}</article>)}
 <ConfirmDialog open={!!review} title="Review employee edit request" message={review?.decision==="approved"?"Apply these proposed values to the official employee profile?":"Reject this request and leave the official profile unchanged?"} confirmDisabled={review?.decision==="rejected"&&!reason.trim()} confirmLabel={review?.decision==="approved"?"Approve change":"Reject change"} onClose={()=>setReview(null)} onConfirm={decide}>
 <FormField label="Review reason" value={reason} required={review?.decision==="rejected"} onChange={e=>setReason(e.target.value)}/>
 </ConfirmDialog></section>;
}
