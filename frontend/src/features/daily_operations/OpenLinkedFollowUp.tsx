import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { apiRequest } from "@/shared/api/client";

export function OpenLinkedFollowUp({ entity, recordId }: { entity: "lead" | "application"; recordId: string }) {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!can("daily_operations:follow-ups", "create") || !can("leads:leads", "view") || (entity === "application" && !can("customer:customers", "view"))) return null;
  return <div><Button size="sm" variant="secondary" disabled={busy} onClick={() => {
    setBusy(true); setError(null);
    void apiRequest<{ id: string }>("/daily-operations/linked-follow-up", { method: "POST", body: JSON.stringify({ entity, record_id: recordId }) })
      .then(row => navigate(`/daily-operations/follow-ups?record=${row.id}`))
      .catch(err => setError(err instanceof Error ? err.message : "Unable to open linked follow-up."))
      .finally(() => setBusy(false));
  }}>{busy ? "Opening…" : "Open Daily Follow-up"}</Button><ErrorBanner message={error} /></div>;
}
