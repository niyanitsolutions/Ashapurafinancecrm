import { Modal } from "@/components/overlays/Modal";
import { MoveToDailyFollowUp } from "@/features/daily_operations/MoveToDailyFollowUp";
import type { LeadListItem } from "@/features/leads/api";
// Retain the existing exported component name for existing callers.
export function MoveApplicationToLoanManagementModal({lead,onClose,onChanged}:{lead:Pick<LeadListItem,"application_id"|"lead_code">;onClose:()=>void;onChanged:()=>void}) {
 return <Modal open title="Move to Daily Follow-up" description={lead.lead_code} onClose={onClose}>{lead.application_id?<MoveToDailyFollowUp applicationId={lead.application_id} onMoved={()=>{onChanged();onClose();}}/>:<p>No Application found.</p>}</Modal>;
}
