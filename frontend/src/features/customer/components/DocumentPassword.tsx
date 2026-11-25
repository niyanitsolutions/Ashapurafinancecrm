import { useEffect, useRef, useState } from "react";
import { usePermissions } from "@/features/access_control/usePermissions";
import { useAuth } from "@/features/auth/useAuth";
import { apiRequest } from "@/shared/api/client";

export function DocumentPassword({ applicationId, documentId }: { applicationId: string; documentId: string }) {
  const { can } = usePermissions();
  const { userId } = useAuth();
  const allowed = can("customer:document_passwords", "view");
  const [value, setValue] = useState("");
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const generation = useRef(0);
  useEffect(() => {
    generation.current++; setValue(""); setError(""); setBusy(false);
    const clear = () => { generation.current++; setValue(""); setBusy(false); };
    window.addEventListener("blur",clear);
    document.addEventListener("visibilitychange",clear);
    return () => { clear(); window.removeEventListener("blur",clear); document.removeEventListener("visibilitychange",clear); };
  },[applicationId,documentId,userId,allowed]);
  useEffect(() => { if(value) { const timer = setTimeout(() => setValue(""),30000); return () => clearTimeout(timer); } },[value]);
  if(!allowed) return null;
  return <span className="flex flex-wrap items-center gap-2 text-xs">
    <span>Password: {value || "\u2022".repeat(8)}</span>
    <button type="button" disabled={busy} className="font-medium text-primary hover:underline" onClick={async () => {
      if(value) { generation.current++; setValue(""); return; }
      const current = ++generation.current; setBusy(true); setError("");
      try { const result = await apiRequest<{ password: string }>(`/applications/${applicationId}/documents/${documentId}/password`, { cache: "no-store" });
        if(generation.current === current) setValue(result.password);
      } catch { if(generation.current === current) setError("Unable to reveal password. Check access or try later."); }
      finally { if(generation.current === current) setBusy(false); }
    }}>{busy ? "Loading..." : value ? "Hide Password" : "Show Password"}</button>
    {error && <span role="alert">{error}</span>}
  </span>;
}
