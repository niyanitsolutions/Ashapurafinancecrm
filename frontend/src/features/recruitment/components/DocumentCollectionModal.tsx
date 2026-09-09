import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { Modal } from "@/components/overlays/Modal";
import {
  NOMINEE_RELATIONSHIPS,
  saveRecruitmentDocuments,
  uploadRecruitmentFile,
  type DocumentSlot,
  type RecruitmentLeadDetail,
  type SaveDocumentsPayload,
} from "@/features/recruitment/api";
import { NOMINEE_RELATIONSHIP_LABELS } from "@/features/recruitment/labels";
import { SignaturePad, type SignatureValue } from "@/features/recruitment/components/SignaturePad";
import { getErrorMessage } from "@/shared/api/errors";

type Confirmed = { s3_key: string; file_name: string };
type FileSlot = Exclude<DocumentSlot, "signature">;

const REQUIRED_DOCS: { slot: FileSlot; label: string }[] = [
  { slot: "pan", label: "PAN Card" },
  { slot: "aadhaar", label: "Unmasked Aadhaar" },
  { slot: "bank_proof", label: "Cheque / Bank Passbook" },
  { slot: "qualification", label: "12th / Intermediate / Degree" },
];

function FileRow({
  label,
  slot,
  leadId,
  existingName,
  onUploaded,
  onError,
}: {
  label: string;
  slot: FileSlot;
  leadId: string;
  existingName?: string | null;
  onUploaded: (slot: FileSlot, file: Confirmed) => void;
  onError: (message: string) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [name, setName] = useState<string | null>(existingName ?? null);

  const onChange = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    try {
      const confirmed = await uploadRecruitmentFile(leadId, slot, file, file.name);
      setName(file.name);
      onUploaded(slot, confirmed);
    } catch (err) {
      onError(getErrorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border px-3.5 py-2.5">
      <div className="min-w-0">
        <p className="text-sm font-medium text-text">{label}</p>
        <p className="truncate text-2xs text-textSecondary">
          {uploading ? "Uploading…" : name ? `Uploaded: ${name}` : "No file uploaded"}
        </p>
      </div>
      <label className="shrink-0 cursor-pointer rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary">
        {name ? "Replace" : "Upload"}
        <input
          type="file"
          className="hidden"
          aria-label={`Upload ${label}`}
          onChange={(e) => onChange(e.target.files?.[0])}
        />
      </label>
    </div>
  );
}

export function DocumentCollectionModal({
  lead,
  onClose,
  onSaved,
}: {
  lead: RecruitmentLeadDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const docs = lead.documents;
  const [files, setFiles] = useState<Partial<Record<FileSlot, Confirmed>>>({});
  const [bankProofType, setBankProofType] = useState<"cheque" | "passbook">(docs?.bank_proof_type ?? "cheque");
  const [chequeNameConfirmed, setChequeNameConfirmed] = useState(docs?.cheque_name_confirmed ?? false);
  const [email, setEmail] = useState(docs?.email ?? lead.email ?? "");
  const [mobile, setMobile] = useState(docs?.mobile ?? lead.mobile ?? "");
  const [altNumber, setAltNumber] = useState(docs?.alternate_number ?? "");
  const [nomineeName, setNomineeName] = useState(docs?.nominee?.name ?? "");
  const [nomineeDob, setNomineeDob] = useState(docs?.nominee?.dob ? docs.nominee.dob.slice(0, 10) : "");
  const [nomineeRelationship, setNomineeRelationship] = useState(docs?.nominee?.relationship ?? "");
  const [signature, setSignature] = useState<SignatureValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onFileUploaded = (slot: FileSlot, file: Confirmed) =>
    setFiles((prev) => ({ ...prev, [slot]: file }));

  // The backend rejects the save (422) unless every required document is present. Mirror
  // that check here so Save is disabled and the reason is visible before the round trip.
  const hasFile = (slot: FileSlot) => Boolean(files[slot] ?? docs?.[slot]);
  const hasSignature = Boolean(signature ?? docs?.signature);
  const missing: string[] = [];
  for (const { slot, label } of REQUIRED_DOCS) if (!hasFile(slot)) missing.push(label);
  if (!hasFile("photo")) missing.push("Passport Size Photo");
  if (!hasSignature) missing.push("Signature");
  if (bankProofType === "cheque" && !chequeNameConfirmed) missing.push("Cheque printed-name confirmation");
  const complete = missing.length === 0;

  const onSave = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload: SaveDocumentsPayload = {
        ...files,
        bank_proof_type: bankProofType,
        cheque_name_confirmed: bankProofType === "cheque" ? chequeNameConfirmed : false,
      };
      if (email.trim()) payload.email = email.trim();
      if (mobile.trim()) payload.mobile = mobile.trim();
      if (altNumber.trim()) payload.alternate_number = altNumber.trim();
      if (nomineeName.trim() && nomineeDob && nomineeRelationship) {
        payload.nominee = { name: nomineeName.trim(), dob: nomineeDob, relationship: nomineeRelationship };
      }

      if (signature) {
        if (signature.method === "type") {
          payload.signature = { method: "type", value: signature.text ?? "" };
        } else if (signature.blob) {
          const confirmed = await uploadRecruitmentFile(
            lead.id,
            "signature",
            signature.blob,
            signature.fileName ?? "signature.png",
          );
          payload.signature = { method: signature.method, value: confirmed.s3_key, file_name: confirmed.file_name };
        }
      }

      await saveRecruitmentDocuments(lead.id, payload);
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const footer = (
    <>
      <Button
        variant="secondary"
        size="sm"
        disabled
        title="Candidate self-upload links are coming soon — collect documents directly for now."
      >
        Generate Link
      </Button>
      <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
        Close
      </Button>
      <Button
        size="sm"
        onClick={onSave}
        loading={busy}
        disabled={!complete}
        title={complete ? undefined : "Please upload all required documents before saving."}
      >
        Save
      </Button>
    </>
  );

  return (
    <Modal
      open
      onClose={onClose}
      title="Document Collection"
      description={`${lead.recruitment_code} · Stage: Doc Collection`}
      size="lg"
      footer={footer}
    >
      {error && <ErrorBanner message={error} />}

      {!complete && (
        <p className="mb-3 rounded-lg bg-warning/10 px-3 py-2 text-2xs text-warning">
          Please upload all required documents before saving. Missing: {missing.join(", ")}.
        </p>
      )}

      <p className="mb-2 text-2xs font-semibold uppercase tracking-wide text-textSecondary">Required documents</p>
      <div className="space-y-2">
        {REQUIRED_DOCS.map(({ slot, label }) => (
          <div key={slot}>
            <FileRow
              label={label}
              slot={slot}
              leadId={lead.id}
              existingName={docs?.[slot]?.file_name}
              onUploaded={onFileUploaded}
              onError={setError}
            />
            {slot === "bank_proof" && (
              <div className="mt-2 rounded-xl bg-background px-3.5 py-3 text-sm">
                <div className="mb-2 flex gap-4">
                  {(["cheque", "passbook"] as const).map((type) => (
                    <label key={type} className="flex cursor-pointer items-center gap-2">
                      <input
                        type="radio"
                        name="bank_proof_type"
                        checked={bankProofType === type}
                        onChange={() => setBankProofType(type)}
                        className="accent-primary"
                      />
                      {type === "cheque" ? "Cheque" : "Bank Passbook"}
                    </label>
                  ))}
                </div>
                {bankProofType === "cheque" && (
                  <label className="flex cursor-pointer items-start gap-2 text-2xs text-textSecondary">
                    <input
                      type="checkbox"
                      checked={chequeNameConfirmed}
                      onChange={(e) => setChequeNameConfirmed(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-border accent-primary"
                    />
                    <span>
                      The cheque shows the printed account-holder name. A cheque without the printed name is not a valid
                      bank proof.
                    </span>
                  </label>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="mb-2 mt-5 text-2xs font-semibold uppercase tracking-wide text-textSecondary">Contact details</p>
      <div className="grid gap-x-4 sm:grid-cols-3">
        <FormField id="rec-doc-email" label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <FormField id="rec-doc-mobile" label="Mobile Number" value={mobile} onChange={(e) => setMobile(e.target.value)} />
        <FormField id="rec-doc-alt" label="Alternate Number" value={altNumber} onChange={(e) => setAltNumber(e.target.value)} />
      </div>

      <p className="mb-2 mt-3 text-2xs font-semibold uppercase tracking-wide text-textSecondary">Nominee details</p>
      <div className="grid gap-x-4 sm:grid-cols-3">
        <FormField id="rec-nominee-name" label="Nominee Name" value={nomineeName} onChange={(e) => setNomineeName(e.target.value)} />
        <FormField
          id="rec-nominee-dob"
          label="Nominee DOB"
          type="date"
          value={nomineeDob}
          onChange={(e) => setNomineeDob(e.target.value)}
        />
        <SelectField
          id="rec-nominee-relationship"
          label="Nominee Relationship"
          value={nomineeRelationship}
          onChange={(e) => setNomineeRelationship(e.target.value)}
          placeholder="Select"
          options={NOMINEE_RELATIONSHIPS.map((r) => ({ value: r, label: NOMINEE_RELATIONSHIP_LABELS[r] }))}
        />
      </div>

      <p className="mb-2 mt-3 text-2xs font-semibold uppercase tracking-wide text-textSecondary">Passport size photo</p>
      <FileRow
        label="Passport Size Photo"
        slot="photo"
        leadId={lead.id}
        existingName={docs?.photo?.file_name}
        onUploaded={onFileUploaded}
        onError={setError}
      />

      <p className="mb-2 mt-4 text-2xs font-semibold uppercase tracking-wide text-textSecondary">Signature</p>
      <SignaturePad
        value={signature}
        existingPreviewUrl={docs?.signature && docs.signature.method !== "type" ? docs.signature.value : null}
        onChange={setSignature}
      />
      {docs?.signature?.method === "type" && !signature && (
        <p className="mt-1 text-2xs text-textSecondary">Current typed signature: “{docs.signature.value}”</p>
      )}
    </Modal>
  );
}
