import { Modal } from "@/components/overlays/Modal";
import { RecordForm } from "./RecordForm";
import { type Row } from "./api";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { apiRequest } from "@/shared/api/client";

export function OpenLinkedFollowUp({ entity, recordId, mode = "navigate", onSaved }: { entity: "lead" | "application"; recordId: string; mode?: "navigate" | "modal"; onSaved?: () => void }) {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const lock=useRef(false);
  const [record,setRecord]=useState<Row | null>(null);
  const [saving,setSaving]=useState(false);
  const [notice,setNotice]=useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!can("daily_operations:follow-ups", "create") || !can("leads:leads", "view") || (entity === "application" && !can("customer:customers", "view"))) return null;
  return <div><Button size="sm" variant="secondary" disabled={busy} onClick={() => {
    if(lock.current)return;lock.current=true;setBusy(true); setError(null);setNotice("");
    void apiRequest<Row>("/daily-operations/linked-follow-up", { method: "POST", body: JSON.stringify({ entity, record_id: recordId }) })
      .then(row => {if(mode === "modal")setRecord(row);else navigate(`/daily-operations/follow-ups?record=${row.id}`);})
      .catch(err => setError(err instanceof Error ? err.message : "Unable to open linked follow-up."))
      .finally(() => {lock.current=false;setBusy(false);});
  }}>{busy ? "Opening…" : "Open Daily Follow-up"}</Button><ErrorBanner message={error} />{notice && <p role="status" className="my-2 text-sm text-success">{notice}</p>}
    {record && <Modal open size="lg" title="Daily Follow-up" onClose={()=>{if(!saving)setRecord(null);}}><RecordForm area="follow-ups" record={record} onSavingChange={setSaving} onCancel={()=>setRecord(null)} onSaved={()=>{setRecord(null);setNotice("Daily follow-up saved.");onSaved?.();}} /></Modal>}
  </div>;
}
