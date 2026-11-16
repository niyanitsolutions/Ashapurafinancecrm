import {useRef, useState} from "react";
import {Button} from "@/components/buttons/Button";
import {useAuth} from "@/features/auth/useAuth";
import {apiRequest} from "@/shared/api/client";
import {getErrorMessage} from "@/shared/api/errors";

export function AirtelTestPanel({ configId, onChanged, disabledReason, savedChallengeId, alreadyVerified, active }: {
  active?: boolean; disabledReason?: string | null; savedChallengeId?: string | null; alreadyVerified?: boolean;
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
  const [otp,setOtp]=useState("");
  const [challenge,setChallenge]=useState<string|null>(null);
  const sentMobile=useRef("");
  async function verify(){
    if(lock.current)return;lock.current=true;setBusy(true);
    try{await apiRequest(`/integration-configs/${configId}/airtel-verify-test-otp`,{method:"POST",body:JSON.stringify({mobile,challenge_id:challenge??savedChallengeId,otp})});setOtp("");setMessage("Test OTP received and verified. You can now Set Active.");onChanged("Test OTP received and verified.");}
    catch(e){setMessage(getErrorMessage(e));}finally{lock.current=false;setBusy(false);}
  }
  async function send() {
    if(lock.current)
      return;
    lock.current = true;
    setBusy(true);
    try {
      const row = await apiRequest<{
        challenge_id: string | null; success: boolean;
        status: string;
        error: string | null;
      }>(`/integration-configs/${configId}/airtel-test-sms`, { method: "POST", body: JSON.stringify({ mobile, confirm_send: confirmed, request_id: crypto.randomUUID() }) });
      if(row.success){setChallenge(row.challenge_id);sentMobile.current=mobile;setConfirmed(false);}
      const notice = row.success ? "Airtel accepted the OTP request. Please check the test mobile for the SMS. Confirm receipt by entering the OTP below." : row.error || row.status;
      setMessage(notice);
      onChanged(notice);
    }
    catch(e) {
      setMessage(getErrorMessage(e));
    }
    finally {
      setConfirmed(false);
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
          name="airtel-explicit-test-mobile" autoComplete="off" disabled={busy} value={mobile} onChange={e => setMobile(e.target.value)} />
      </label>
      <label className="block">
        <input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />
        {" "}I authorize sending the approved test SMS to this number.
      </label>
      <Button disabled={busy || Boolean(disabledReason) || !confirmed || !/^[6-9][0-9]{9}$/.test(mobile)} onClick={() => void send()}>Send test SMS</Button>
      {disabledReason && <p>{disabledReason}</p>}
      <p role="status">{message}</p>
      {!alreadyVerified && (challenge || savedChallengeId) && <div className="space-y-2"><p>Enter the OTP received on the test mobile. It expires in 10 minutes and can be used once.</p><label>Received test OTP<input name="airtel-test-otp" autoComplete="one-time-code" type="password" inputMode="numeric" maxLength={4} value={otp} onChange={e=>setOtp(e.target.value)}/></label><Button disabled={busy || Boolean(disabledReason) || !/^[0-9]{4}$/.test(otp) || !/^[6-9][0-9]{9}$/.test(mobile) || Boolean(sentMobile.current && sentMobile.current!==mobile)} onClick={()=>void verify()}>Verify test OTP</Button></div>}

      {role === "owner" && (
        <div className="border-t border-border pt-3">
          <h3 className="font-semibold">Retire customer password sign-in</h3>
          <p className="text-sm">Every active customer account must have a PIN, and Airtel must be tested and active. This customer-only cutover has no password fallback. Employee and partner sign-in stays unchanged.</p>
          <label className="block my-2">
            <input type="checkbox" checked={cutoverConfirmed} disabled={busy} onChange={e => setCutoverConfirmed(e.target.checked)} />
            {" "}I confirm all active customers have enrolled and authorize customer PIN-only sign-in.
          </label>
          {(!alreadyVerified || !active) && <p>Verify the test OTP and Set Active before authorizing a separate customer PIN-only cutover.</p>}
          <Button disabled={!cutoverConfirmed || busy || !alreadyVerified || !active} onClick={() => void cutover()}>Enable customer PIN-only sign-in</Button>
        </div>
      )}
    </section>
  );
}
