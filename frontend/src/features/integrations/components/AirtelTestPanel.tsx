import {useRef, useState} from "react";
import {Button} from "@/components/buttons/Button";
import {useAuth} from "@/features/auth/useAuth";
import {apiRequest} from "@/shared/api/client";
import {getErrorMessage} from "@/shared/api/errors";

export function AirtelTestPanel({ configId, onChanged }: {
  configId: string;
  onChanged: (message: string) => void;
}) {
  const { role } = useAuth();
  const [cutoverConfirmed, setCutoverConfirmed] = useState(false);
  async function cutover() {
    if(lock.current)
      return;
    lock.current = true;
    setBusy(true);
    try {
      await apiRequest("/auth/pin/cutover", { method: "POST" });
      setMessage("PIN-only sign-in is enabled. Customer password sign-in is retired.");
    }
    catch(e) {
      setMessage(getErrorMessage(e));
    }
    finally {
      lock.current = false;
      setBusy(false);
    }
  }
  const [mobile, setMobile] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  async function send() {
    if(lock.current)
      return;
    lock.current = true;
    setBusy(true);
    try {
      const row = await apiRequest<{
        success: boolean;
        status: string;
        error: string | null;
      }>(`/integration-configs/${configId}/airtel-test-sms`, { method: "POST", body: JSON.stringify({ mobile, confirm_send: confirmed, request_id: crypto.randomUUID() }) });
      const notice = row.success ? "Airtel accepted the submission. Confirm receipt on the test phone before treating SMS as live." : row.error || row.status;
      setMessage(notice);
      onChanged(notice);
    }
    catch(e) {
      setMessage(getErrorMessage(e));
    }
    finally {
      lock.current = false;
      setBusy(false);
    }
  }
  if (role !== "owner") return null;
  return (
    <section className="mb-4 space-y-3 rounded-lg border border-border p-4">
      <h3 className="font-semibold">Explicit Airtel test SMS</h3>
      <label className="block">Test mobile number
        <input className="ml-2 rounded border border-border p-2" inputMode="numeric" maxLength={10}
          disabled={busy} value={mobile} onChange={e => setMobile(e.target.value)} />
      </label>
      <label className="block">
        <input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />
        {" "}I authorize sending the approved test SMS to this number.
      </label>
      <Button disabled={busy || !confirmed || !/^[6-9][0-9]{9}$/.test(mobile)} onClick={() => void send()}>Send test SMS</Button>
      <p role="status">{message}</p>
      {role === "owner" && (
        <div className="border-t border-border pt-3">
          <h3 className="font-semibold">Retire customer password sign-in</h3>
          <p className="text-sm">Every active customer account must have a PIN, and Airtel must be tested and active. This customer-only cutover has no password fallback. Employee and partner sign-in stays unchanged.</p>
          <label className="block my-2">
            <input type="checkbox" checked={cutoverConfirmed} disabled={busy} onChange={e => setCutoverConfirmed(e.target.checked)} />
            {" "}I confirm all active customers have enrolled and authorize customer PIN-only sign-in.
          </label>
          <Button disabled={!cutoverConfirmed || busy} onClick={() => void cutover()}>Enable customer PIN-only sign-in</Button>
        </div>
      )}
    </section>
  );
}
