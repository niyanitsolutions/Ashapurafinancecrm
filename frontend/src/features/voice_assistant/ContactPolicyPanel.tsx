import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/useAuth";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { getErrorMessage } from "@/shared/api/errors";
import { getContactPolicies, saveContactConsent, saveContactSuppression } from "./api";

export function ContactPolicyPanel() {
  const { role, userId } = useAuth(); const cache = useQueryClient();
  const [inputId, setInputId] = useState(""); const [customerId, setCustomerId] = useState("");
  const [purpose, setPurpose] = useState("service_callback"); const [reference, setReference] = useState("");
  const [expiry, setExpiry] = useState(""); const [reason, setReason] = useState("");
  const key = ["voice", userId, "contact-policies", customerId];
  const query = useQuery({ queryKey: key, queryFn: () => getContactPolicies(customerId), enabled: role === "owner" && !!customerId });
  const mutation = useMutation({ mutationFn: async (action: "grant" | "withdraw" | "suppress" | "unsuppress") => {
    if (!query.data) throw new Error("Load the current customer policies before changing them.");
    if (action === "grant" || action === "withdraw") {
      const current = query.data.consents.find(item => item.purpose === purpose);
      if (action === "grant" && !expiry) throw new Error("Enter an expiry with an explicit UTC offset.");
      return saveContactConsent({ customer_id: customerId, version: current?.version ?? 1, purpose, action, evidence_reference: reference, expires_at: action === "grant" ? expiry : null });
    }
    const current = query.data.suppressions.find(item => item.scope === "global");
    return saveContactSuppression({ customer_id: customerId, version: current?.version ?? 1, suppressed: action === "suppress", reason });
  }, onSuccess: () => cache.invalidateQueries({ queryKey: key }) });
  if (role !== "owner") return <p>Voice contact policy attestation is restricted to the Owner.</p>;
  return <section className="bg-card border rounded-xl p-5 space-y-4"><h2 className="font-semibold">Voice consent and suppression</h2>
    <p>These records are operator attestations. They do not independently verify customer consent, DND eligibility or regulatory approval. Live dispatch remains blocked.</p>
    <ErrorBanner message={query.error || mutation.error ? getErrorMessage(query.error ?? mutation.error) : null} />
    <form onSubmit={e => { e.preventDefault(); setCustomerId(inputId); }}><label>Existing CRM customer ID<input className="block border rounded p-2 w-full" required pattern="[a-f0-9]{24}" value={inputId} onChange={e => setInputId(e.target.value)} /></label><button>Load policies</button></form>
    {query.data && <><div>{query.data.consents.map(item => <p key={item.id}>{item.purpose}: {item.action}, version {item.version}, {item.verification}</p>)}{query.data.suppressions.map(item => <p key={item.id}>{item.scope}: {item.suppressed ? "suppressed" : "not suppressed"}, version {item.version}</p>)}</div>
      <label>Purpose identifier<input className="block border rounded p-2 w-full" value={purpose} onChange={e => setPurpose(e.target.value)} /></label>
      <label>Evidence reference<input className="block border rounded p-2 w-full" value={reference} maxLength={150} onChange={e => setReference(e.target.value)} /></label>
      <label>Consent expiry (ISO timestamp with offset)<input className="block border rounded p-2 w-full" placeholder="2026-12-01T18:00:00+05:30" value={expiry} onChange={e => setExpiry(e.target.value)} /></label>
      <div className="flex gap-3"><button disabled={mutation.isPending || reference.length < 5} onClick={() => mutation.mutate("grant")}>Record consent attestation</button><button disabled={mutation.isPending || reference.length < 5} onClick={() => mutation.mutate("withdraw")}>Withdraw consent</button></div>
      <label>Suppression change reason<input className="block border rounded p-2 w-full" value={reason} maxLength={160} onChange={e => setReason(e.target.value)} /></label>
      <div className="flex gap-3"><button disabled={mutation.isPending || reason.length < 5} onClick={() => mutation.mutate("suppress")}>Suppress voice contact</button><button disabled={mutation.isPending || reason.length < 5} onClick={() => mutation.mutate("unsuppress")}>Remove suppression</button></div>
    </>}
  </section>;
}
