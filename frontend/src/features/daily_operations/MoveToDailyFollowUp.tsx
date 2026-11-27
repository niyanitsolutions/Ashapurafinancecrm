import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { useAuth } from "@/features/auth/useAuth";
import { apiRequest } from "@/shared/api/client";
import { base, type Row } from "./api";
export function MoveToDailyFollowUp({applicationId,onMoved}:{applicationId:string;onMoved?:()=>void}) {
 const {can}=usePermissions(); const {userId}=useAuth(); const client=useQueryClient();const [busy,setBusy]=useState(false);const [error,setError]=useState<string|null>(null);const lock=useRef(false);
 const query=useQuery({queryKey:["application-workspace",userId,applicationId],enabled:can("daily_operations:follow-ups","view"),queryFn:()=>apiRequest<Row>(`${base}/applications/${applicationId}/workspace`)});
 const moved=query.data?.movement_status==="Moved to Daily Follow-up";
 async function move(){if(lock.current)return;lock.current=true;setBusy(true);setError(null);try{await apiRequest(`${base}/applications/${applicationId}/move`,{method:"POST"});await client.invalidateQueries({queryKey:["application-workspace",userId,applicationId]});await client.invalidateQueries({queryKey:["daily-operations"]});onMoved?.();}catch(e){setError(e instanceof Error?e.message:"Movement failed.");}finally{setBusy(false);lock.current=false;}}
 return <section className="space-y-2 rounded-lg border border-border p-3"><p className="text-xs">Application: {applicationId} | {String(query.data?.movement_status||"Movement status unavailable")}</p><ErrorBanner message={error}/>{moved&&query.data?.id?<Link className="text-primary underline" to={`/daily-operations/follow-ups?record=${query.data.id}`}>Open Daily Follow-up</Link>:can("customer:customers","edit")&&can("daily_operations:follow-ups","create")&&<Button loading={busy} onClick={()=>void move()}>Move to Daily Follow-up</Button>}<p className="text-xs text-textSecondary">Document verification is preserved. Movement does not approve or disburse this Application.</p></section>;
}
