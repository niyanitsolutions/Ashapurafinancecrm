import type { ReactNode } from "react";
import { Badge } from "@/components/badges/Badge";
import type { RecruitmentLeadDetail } from "@/features/recruitment/api";
import { EXAM_LABELS, GENDER_LABELS, NOMINEE_RELATIONSHIP_LABELS, professionLabel } from "@/features/recruitment/labels";
import { formatISTDate, formatISTDateTime } from "@/shared/dateFormat";

// Shared read-only panels for a recruitment lead — rendered on both RecruitmentDetailsPage
// and (for a promoted advisor) AdvisorDetailsPage, so the recruitment / document /
// examination view is defined once.

export function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <span className="text-textSecondary">{label}</span>
      <span className="text-right font-medium text-text">{value || "—"}</span>
    </div>
  );
}

export function Panel({ title, className = "", children }: { title: string; className?: string; children: ReactNode }) {
  return (
    <section className={`rounded-2xl border border-border bg-card p-4 ${className}`}>
      <h2 className="mb-2 text-sm font-bold text-text">{title}</h2>
      {children}
    </section>
  );
}

const DOC_LABELS: Record<string, string> = {
  pan: "PAN Card",
  aadhaar: "Unmasked Aadhaar",
  bank_proof: "Cheque / Bank Passbook",
  qualification: "12th / Intermediate / Degree",
  photo: "Passport Photo",
};

export function PersonalInfoPanel({ lead }: { lead: RecruitmentLeadDetail }) {
  return (
    <Panel title="Personal information">
      <InfoRow label="Mobile" value={lead.mobile} />
      <InfoRow label="Email" value={lead.email} />
      <InfoRow label="Gender" value={GENDER_LABELS[lead.gender] ?? lead.gender} />
      <InfoRow label="Age" value={lead.age} />
      <InfoRow label="Source" value={lead.source_name} />
      <InfoRow label="Profession" value={professionLabel(lead.profession, lead.other_profession)} />
      <InfoRow label="Remarks" value={lead.remarks} />
      <InfoRow label="Assigned to" value={lead.assigned_to_name} />
      {lead.rejected_reason && <InfoRow label="Rejection reason" value={lead.rejected_reason} />}
    </Panel>
  );
}

export function DocumentCollectionPanel({ lead }: { lead: RecruitmentLeadDetail }) {
  const docs = lead.documents;
  return (
    <Panel title="Document collection">
      {docs ? (
        <>
          {["pan", "aadhaar", "bank_proof", "qualification", "photo"].map((slot) => {
            const file = (docs as unknown as Record<string, { file_name: string; download_url: string | null } | null>)[slot];
            return (
              <div key={slot} className="flex justify-between gap-4 py-1.5 text-sm">
                <span className="text-textSecondary">{DOC_LABELS[slot]}</span>
                {file ? (
                  file.download_url ? (
                    <a href={file.download_url} target="_blank" rel="noreferrer" className="font-medium text-info hover:underline">
                      {file.file_name}
                    </a>
                  ) : (
                    <span className="font-medium text-text">{file.file_name}</span>
                  )
                ) : (
                  <span className="text-textSecondary">Not uploaded</span>
                )}
              </div>
            );
          })}
          <InfoRow
            label="Bank proof type"
            value={
              docs.bank_proof_type
                ? `${docs.bank_proof_type === "cheque" ? "Cheque" : "Bank Passbook"}${
                    docs.bank_proof_type === "cheque"
                      ? docs.cheque_name_confirmed
                        ? " (name confirmed)"
                        : " (name NOT confirmed)"
                      : ""
                  }`
                : null
            }
          />
          <InfoRow label="Contact email" value={docs.email} />
          <InfoRow label="Contact mobile" value={docs.mobile} />
          <InfoRow label="Alternate number" value={docs.alternate_number} />
          {docs.nominee && (
            <InfoRow
              label="Nominee"
              value={`${docs.nominee.name} · ${formatISTDate(docs.nominee.dob)} · ${
                NOMINEE_RELATIONSHIP_LABELS[docs.nominee.relationship] ?? docs.nominee.relationship
              }`}
            />
          )}
          <InfoRow
            label="Signature"
            value={
              docs.signature
                ? docs.signature.method === "type"
                  ? `Typed: ${docs.signature.value}`
                  : docs.signature.value
                    ? (
                        <a href={docs.signature.value} target="_blank" rel="noreferrer" className="text-info hover:underline">
                          View image
                        </a>
                      )
                    : "Captured"
                : null
            }
          />
          <InfoRow label="Documents ready" value={lead.documents_ready ? "Yes" : "No"} />
        </>
      ) : (
        <p className="text-sm text-textSecondary">No documents collected yet.</p>
      )}
    </Panel>
  );
}

export function ExaminationHistoryPanel({ lead }: { lead: RecruitmentLeadDetail }) {
  if (lead.examinations.length === 0) return null;
  return (
    <Panel title="Examination history">
      {lead.examinations.map((exam) => (
        <div key={exam.attempt} className="flex justify-between gap-4 py-1.5 text-sm">
          <span className="text-textSecondary">
            Attempt {exam.attempt} · {formatISTDateTime(exam.recorded_at)}
          </span>
          <span className="text-right">
            <Badge tone={exam.result === "pass" ? "success" : "danger"}>{EXAM_LABELS[exam.result]}</Badge>
            {exam.remarks ? <span className="ml-2 text-textSecondary">{exam.remarks}</span> : null}
          </span>
        </div>
      ))}
    </Panel>
  );
}
