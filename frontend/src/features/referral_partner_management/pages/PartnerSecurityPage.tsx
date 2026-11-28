import { useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "@/shared/api/client";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";

export function PartnerSecurityPage() {
  const [current,setCurrent]=useState("");const [password,setPassword]=useState("");const [confirm,setConfirm]=useState("");const [show,setShow]=useState(false);const [error,setError]=useState<string|null>(null);const [notice,setNotice]=useState("");const [busy,setBusy]=useState(false);
  return <section className="mx-auto max-w-xl space-y-4"><h1 className="text-2xl font-semibold">Profile &amp; Security</h1><ErrorBanner message={error}/>{notice&&<p role="status">{notice}</p>}<form className="space-y-4 rounded-xl border border-border bg-card p-5" onSubmit={e=>{e.preventDefault();setError(null);if(password!==confirm){setError("Passwords do not match.");return;}setBusy(true);void apiRequest("/auth/change-password",{method:"POST",body:JSON.stringify({current_password:current,new_password:password})}).then(()=>{setCurrent("");setPassword("");setConfirm("");setNotice("Password changed.");}).catch(e=>setError(e.message)).finally(()=>setBusy(false));}}>
    <FormField label="Current password" type={show?"text":"password"} autoComplete="current-password" value={current} onChange={e=>setCurrent(e.target.value)} required/>
    <FormField label="New password" type={show?"text":"password"} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)} required/>
    <FormField label="Confirm new password" type={show?"text":"password"} autoComplete="new-password" value={confirm} onChange={e=>setConfirm(e.target.value)} required/>
    <label><input type="checkbox" checked={show} onChange={e=>setShow(e.target.checked)}/>Show passwords</label><Button type="submit" loading={busy}>Change password</Button>
    </form><Link className="text-primary underline" to="/forgot-password">Forgot password</Link><Link className="ml-4 text-primary underline" to="/referral-portal/kyc">Profile and KYC information</Link></section>;
}
