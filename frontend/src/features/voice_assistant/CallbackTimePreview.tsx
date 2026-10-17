import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { getErrorMessage } from "@/shared/api/errors";
import { previewCallbackTime, type CallbackTimePreview as Preview } from "./callbackApi";

export function CallbackTimePreview({ request, timezone, disabled, apply }: { request: string; timezone: string; disabled: boolean; apply: (value: string) => void }) {
  const [result, setResult] = useState<{ value: Preview; request: string; timezone: string } | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const current = result?.request === request && result.timezone === timezone ? result.value : null;
  return <div className="space-y-2">
    <Button variant="secondary" disabled={disabled || busy || request.length < 5} onClick={async () => {
      setBusy(true); setError(""); setResult(null);
      try { setResult({ value: await previewCallbackTime(request, timezone), request, timezone }); }
      catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
    }}>Preview requested time</Button>
    <p className="text-sm">English date preview only. Ambiguous requests need clarification. A preview saves nothing and never places a call.</p>
    {error && <p role="alert">{error}</p>}
    {current && <div role="status" className="text-sm space-y-2"><p>{current.clarification}</p>{current.interpreted_date && <p>Interpreted date: {current.interpreted_date} ({current.timezone})</p>}{current.requested_local && <><p>Proposed local time: {current.requested_local.replace("T", " ")} ({current.timezone})</p><Button variant="secondary" disabled={disabled || busy} onClick={() => apply(current.requested_local!.slice(0, 16))}>Use proposed time in form</Button></>}</div>}
  </div>;
}
