import { useEffect, useState } from "react";
import { apiRequestRaw } from "@/shared/api/client";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Modal } from "@/components/overlays/Modal";

interface EarningEvent {
  id?: string; kind: string; amount: number; base_amount?: number; rate_or_amount?: number;
  calculation_type?: string; fixed_event_policy?: string; rule_version?: number; rule_id?: string;
  financial_at?: string; created_at?: string; disbursement_event_id?: string;
}

export function CommissionHistoryDialog({ entryId, onClose }: { entryId: string; onClose: () => void }) {
  const [data, setData] = useState<{original:EarningEvent;events:EarningEvent[]} | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  useEffect(() => {
    let current = true;
    void apiRequestRaw<{original:EarningEvent;events:EarningEvent[]}>(`/commission-entries/${entryId}/history?page=${page}&page_size=20`).then(response => {
      if (current) { setData(response.data??null); setTotal(response.meta?.pagination?.total??0); }
    }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [entryId, page]);
  const date = (value?:string) => value ? new Date(value).toLocaleString("en-IN", {timeZone:"Asia/Kolkata"}) : "Not recorded";
  return <Modal open onClose={onClose} title="Commission earning history" size="lg"><div className="space-y-4"><ErrorBanner message={error}/><p className="text-sm">Original earnings and later tranche rates remain unchanged. Adjustments are separate signed entries. Confirmed payments appear in Payout History.</p>
    {!data?<p role="status">Loading earning history…</p>:<div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr>{["Event","Financial date (IST)","Calculated / recorded (IST)","Eligible base","Rate / contract","Rule version","Amount"].map(label=><th className="p-2 text-left" key={label}>{label}</th>)}</tr></thead><tbody>{[data.original,...data.events].map((event,index)=><tr className="border-t border-border" key={event.id??`${event.kind}-${index}`}><td className="p-2">{event.kind.replaceAll("_"," ")}{event.disbursement_event_id&&<p className="text-xs">Financial reference: {event.disbursement_event_id}</p>}</td><td className="p-2">{date(event.financial_at)}</td><td className="p-2">{date(event.created_at)}</td><td className="p-2">{event.base_amount===undefined?"—":event.base_amount.toLocaleString("en-IN")}</td><td className="p-2">{event.rate_or_amount===undefined?"—":`${event.rate_or_amount}${event.calculation_type==="percentage"?"%":" fixed"}`}{event.fixed_event_policy&&<p>{event.fixed_event_policy.replaceAll("_"," ")}</p>}</td><td className="p-2">{event.rule_version??"—"}</td><td className="p-2">₹{event.amount.toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2})}</td></tr>)}</tbody></table></div>}
    <div className="flex gap-3"><Button variant="secondary" disabled={page===1} onClick={()=>setPage(page-1)}>Previous events</Button><span>Page {page}</span><Button variant="secondary" disabled={page*20>=total} onClick={()=>setPage(page+1)}>Next events</Button></div>
  </div></Modal>;
}
