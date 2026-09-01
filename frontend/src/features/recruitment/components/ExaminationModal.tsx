import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import {
  moveRecruitmentToAdvisor,
  recordRecruitmentExamination,
  rejectRecruitmentLead,
  type ExaminationOutcome,
  type RecruitmentLeadDetail,
} from "@/features/recruitment/api";
import { getErrorMessage } from "@/shared/api/errors";

const RESULTS: { value: ExaminationOutcome; label: string }[] = [
  { value: "pass", label: "PASS" },
  { value: "fail", label: "FAIL" },
  { value: "absent", label: "ABSENT" },
];

export function ExaminationModal({
  lead,
  onClose,
  onSaved,
}: {
  lead: RecruitmentLeadDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [result, setResult] = useState<ExaminationOutcome | "">("");
  const [remarks, setRemarks] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);

  const previous = lead.examinations[lead.examinations.length - 1] ?? null;
  const remarksRequired = result === "fail" || result === "absent";
  const canSubmit = result !== "" && (!remarksRequired || remarks.trim().length > 0);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = () =>
    run(() =>
      recordRecruitmentExamination(lead.id, {
        result: result as ExaminationOutcome,
        remarks: remarks.trim() || undefined,
      }),
    );

  const onMoveToAdvisor = () => run(() => moveRecruitmentToAdvisor(lead.id));
  const onConfirmReject = () => run(() => rejectRecruitmentLead(lead.id, remarks.trim() || "Rejected at examination."));

  const footer = rejecting ? (
    <>
      <Button variant="secondary" size="sm" onClick={() => setRejecting(false)} disabled={busy}>
        Back
      </Button>
      <Button variant="danger" size="sm" onClick={onConfirmReject} loading={busy}>
        Confirm Reject
      </Button>
    </>
  ) : (
    <>
      <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
        Close
      </Button>
      <Button variant="danger" size="sm" onClick={() => setRejecting(true)} disabled={busy}>
        Reject
      </Button>
      {previous?.result === "pass" && lead.advisor_id == null && (
        <Button variant="secondary" size="sm" onClick={onMoveToAdvisor} loading={busy}>
          Move to Advisor
        </Button>
      )}
      <Button size="sm" onClick={onSubmit} loading={busy} disabled={!canSubmit}>
        Submit
      </Button>
    </>
  );

  return (
    <Modal
      open
      onClose={onClose}
      title="Examination Result"
      description={`${lead.recruitment_code} · ${lead.full_name}`}
      footer={footer}
    >
      {error && <ErrorBanner message={error} />}

      {previous && (
        <div className="mb-4 rounded-xl bg-background px-3.5 py-2.5 text-sm">
          <p className="text-textSecondary">
            Previous result: <span className="font-semibold text-text">{previous.result.toUpperCase()}</span>
            {previous.remarks ? ` — ${previous.remarks}` : ""}
          </p>
          <p className="text-2xs text-textSecondary">Attempt {previous.attempt}</p>
        </div>
      )}

      {rejecting ? (
        <TextareaField
          label="Rejection remarks"
          id="exam-reject-remarks"
          rows={3}
          value={remarks}
          onChange={(e) => setRemarks(e.target.value)}
          placeholder="Reason for rejecting at examination"
        />
      ) : (
        <>
          {!lead.documents_ready && (
            <p className="mb-3 text-sm text-danger">
              All required documents, a photo and a signature must be collected before a PASS can be recorded.
            </p>
          )}
          <div className="mb-3 flex gap-2">
            {RESULTS.map((r) => (
              <button
                key={r.value}
                type="button"
                onClick={() => setResult(r.value)}
                className={`flex-1 rounded-xl border py-2.5 text-sm font-semibold transition-colors ${
                  result === r.value
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-textSecondary hover:bg-background"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          {remarksRequired && (
            <TextareaField
              label="Remarks"
              id="exam-remarks"
              rows={3}
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
              placeholder={result === "fail" ? "Why did the candidate not clear the examination?" : "Why was the candidate absent?"}
            />
          )}
          {result === "pass" && (
            <p className="text-2xs text-textSecondary">
              On submit, the candidate is promoted to Advisor automatically.
            </p>
          )}
        </>
      )}
    </Modal>
  );
}
