import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { Modal } from "@/components/overlays/Modal";
import { usePermissions } from "@/features/access_control/usePermissions";
import { type Customer } from "@/features/customer/api";
import { apiRequest } from "@/shared/api/client";
import { formatISTDate } from "@/shared/dateFormat";

export function StaffCustomerProfile({ customerId }: { customerId: string }) {
  const { can, isOwner } = usePermissions();
  const [profile,setProfile] = useState<(Customer & { version: number }) | null>(null);
  const [editing,setEditing] = useState(false);
  const [form,setForm] = useState({ full_name: "", email: "", date_of_birth: "", pan_number: "", reason: "" });
  const [error,setError] = useState<string | null>(null);
  const [busy,setBusy] = useState(false);
  useEffect(() => { let active = true; apiRequest<Customer & { version: number }>(`/customers/${customerId}`).then(p => { if(active) setProfile(p); }).catch(e => { if(active) setError(e.message); }); return () => { active = false; }; },[customerId]);
  return <section className="rounded-card border border-border bg-card p-6">
    <h2 className="mb-3 font-semibold">Customer Details - current profile</h2><ErrorBanner message={error} />
    {profile && <><Link className="text-primary underline" to={`/leads/document-collection?customer_id=${customerId}&expand=${customerId}`}>{profile.customer_code}</Link><p>{profile.full_name}</p><p>{profile.mobile}</p><p>{profile.email}</p>{profile.date_of_birth && <p>Date of birth: {formatISTDate(profile.date_of_birth)}</p>}<p>PAN: {profile.pan_number_masked || "Not provided"}</p>
      <p className="my-3 text-xs text-textSecondary">Current shared identity. Original application answers remain in the application record below.</p>
      {can("customer:customers","edit") && <Button size="sm" variant="secondary" onClick={() => { setForm({ full_name: profile.full_name, email: profile.email || "", date_of_birth: profile.date_of_birth || "", pan_number: "", reason: "" }); setEditing(true); }}>Edit Customer Details</Button>}
    </>}
    {editing && profile && <Modal open title="Edit current customer profile" onClose={() => { if(!busy) setEditing(false); }}><form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(null); try {
      const body = { version: profile.version, full_name: form.full_name, email: form.email || null, reason: form.reason,
        ...(isOwner ? { date_of_birth: form.date_of_birth || null, ...(form.pan_number ? { pan_number: form.pan_number } : {}) } : {}) };
      setProfile(await apiRequest<Customer & { version: number }>(`/customers/${customerId}`, { method: "PATCH", body: JSON.stringify(body) })); setEditing(false);
    } catch(err) { setError(err instanceof Error ? err.message : "Unable to save customer."); } finally { setBusy(false); } }}>
      <ErrorBanner message={error} /><FormField label="Full name" required value={form.full_name} onChange={e => setForm(f => ({...f,full_name:e.target.value}))} />
      <FormField label="Email" type="email" value={form.email} onChange={e => setForm(f => ({...f,email:e.target.value}))} />
      {isOwner && <><FormField label="Date of birth" type="date" value={form.date_of_birth} onChange={e => setForm(f => ({...f,date_of_birth:e.target.value}))} /><FormField label="Replace PAN (leave blank to retain)" value={form.pan_number} maxLength={10} pattern="[A-Z]{5}[0-9]{4}[A-Z]" onChange={e => setForm(f => ({...f,pan_number:e.target.value.toUpperCase()}))} /></>}
      <FormField label="Reason for change" required minLength={3} maxLength={500} value={form.reason} onChange={e => setForm(f => ({...f,reason:e.target.value}))} /><div className="flex gap-3"><Button type="submit" loading={busy}>Save profile</Button><Button variant="secondary" disabled={busy} onClick={() => setEditing(false)}>Cancel</Button></div>
    </form></Modal>}
  </section>;
}
