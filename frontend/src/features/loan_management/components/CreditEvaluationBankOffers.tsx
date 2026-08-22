import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { TextareaField } from "@/components/forms/TextareaField";
import { getErrorMessage } from "@/features/customer/errors";
import {
  addBankOffer,
  listBankOffers,
  selectBankOffer,
  updateBankOffer,
  type BankOffer,
  type BankOfferPayload,
} from "@/features/loan_management/api";

const DECISION_LABELS: Record<string, string> = { approved: "Approved", rejected_re_eligible: "Rejected / Re-Eligible" };

// Credit Evaluation's dedicated Type B update view (spec §6-8): a Loan Case can carry
// any number of bank/NBFC offers — adding one never overwrites another — each with an
// independent decision (Approved requires an amount; Rejected/Re-Eligible never does).
// Selecting one is a SEPARATE step from confirming acceptance (see OfferAcceptancePanel)
// — this component only ever selects, never confirms.
export function CreditEvaluationBankOffers({ caseId, canEdit, onOfferSelected }: { caseId: string; canEdit: boolean; onOfferSelected: () => void }) {
  const [offers, setOffers] = useState<BankOffer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editingOffer, setEditingOffer] = useState<BankOffer | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [confirmSelectId, setConfirmSelectId] = useState<string | null>(null);

  const load = () => {
    listBankOffers(caseId).then(setOffers).catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [caseId]);

  const handleAdd = async (payload: BankOfferPayload) => {
    setError(null);
    try {
      await addBankOffer(caseId, payload);
      setShowAddForm(false);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleEdit = async (payload: BankOfferPayload) => {
    if (!editingOffer) return;
    setError(null);
    try {
      await updateBankOffer(caseId, editingOffer.id, payload);
      setEditingOffer(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleSelect = async (offerId: string) => {
    setError(null);
    try {
      await selectBankOffer(caseId, offerId);
      setConfirmSelectId(null);
      onOfferSelected();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <div className="space-y-3">
      {error && <p className="text-sm text-danger">{error}</p>}

      {offers.length === 0 && <p className="text-sm text-text/40">No bank/NBFC offers recorded yet.</p>}

      {offers.map((offer) =>
        editingOffer?.id === offer.id ? (
          <BankOfferForm key={offer.id} initial={offer} onSubmit={handleEdit} onCancel={() => setEditingOffer(null)} />
        ) : (
          <div key={offer.id} className="rounded border border-border p-3 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-medium text-text">{offer.bank_name}</span>
              {offer.is_selected && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-2xs font-semibold text-primary">Selected</span>}
            </div>
            <div className="text-sm text-text/70">
              Status: {DECISION_LABELS[offer.decision] ?? offer.decision}
              {offer.decision === "approved" && offer.approved_amount != null && (
                <span> — Approved Amount: ₹{offer.approved_amount.toLocaleString("en-IN")}</span>
              )}
            </div>
            {canEdit && (
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="secondary" onClick={() => setEditingOffer(offer)}>
                  Edit
                </Button>
                {offer.decision === "approved" && !offer.is_selected && (
                  <Button size="sm" onClick={() => setConfirmSelectId(offer.id)}>
                    Select
                  </Button>
                )}
              </div>
            )}
          </div>
        )
      )}

      {canEdit && !showAddForm && (
        <Button size="sm" variant="secondary" onClick={() => setShowAddForm(true)}>
          + Add Other Bank
        </Button>
      )}
      {canEdit && showAddForm && <BankOfferForm onSubmit={handleAdd} onCancel={() => setShowAddForm(false)} />}

      <ConfirmDialog
        open={confirmSelectId !== null}
        title="Select This Offer"
        message="Select this bank offer as the case's final offer? The case will move to Offer Acceptance. This does not yet confirm acceptance — a separate confirmation step is still required."
        confirmLabel="Select Offer"
        onConfirm={() => {
          if (confirmSelectId) return handleSelect(confirmSelectId);
        }}
        onClose={() => setConfirmSelectId(null)}
      />
    </div>
  );
}

function BankOfferForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: BankOffer;
  onSubmit: (payload: BankOfferPayload) => void;
  onCancel: () => void;
}) {
  const [bankName, setBankName] = useState(initial?.bank_name ?? "");
  const [bankApplicationId, setBankApplicationId] = useState(initial?.bank_application_id ?? "");
  const [referenceNumber, setReferenceNumber] = useState(initial?.reference_number ?? "");
  const [assignedOfficer, setAssignedOfficer] = useState(initial?.assigned_officer ?? "");
  const [decision, setDecision] = useState<"approved" | "rejected_re_eligible">((initial?.decision as "approved" | "rejected_re_eligible") ?? "approved");
  const [approvedAmount, setApprovedAmount] = useState(initial?.approved_amount != null ? String(initial.approved_amount) : "");
  const [remarks, setRemarks] = useState(initial?.remarks ?? "");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          bank_name: bankName,
          bank_application_id: bankApplicationId || undefined,
          reference_number: referenceNumber || undefined,
          assigned_officer: assignedOfficer || undefined,
          decision,
          approved_amount: decision === "approved" ? Number(approvedAmount) : undefined,
          remarks: remarks || undefined,
        });
      }}
      className="rounded border border-border p-3 space-y-2"
    >
      <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
        <FormField label="Bank/NBFC" value={bankName} onChange={(e) => setBankName(e.target.value)} required />
        <FormField label="Bank Application ID" value={bankApplicationId} onChange={(e) => setBankApplicationId(e.target.value)} />
        <FormField label="Reference Number" value={referenceNumber} onChange={(e) => setReferenceNumber(e.target.value)} />
        <FormField label="Assigned Officer" value={assignedOfficer} onChange={(e) => setAssignedOfficer(e.target.value)} />
      </div>
      <TextareaField label="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
      <SelectField
        label="Bank Decision"
        value={decision}
        onChange={(e) => setDecision(e.target.value as "approved" | "rejected_re_eligible")}
        options={[
          { value: "approved", label: "Approved" },
          { value: "rejected_re_eligible", label: "Rejected / Re-Eligible" },
        ]}
      />
      {decision === "approved" && (
        <FormField label="Approved Amount" type="number" value={approvedAmount} onChange={(e) => setApprovedAmount(e.target.value)} required />
      )}
      <div className="flex gap-2">
        <SubmitButton>Save Bank</SubmitButton>
        <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
