import { Button } from "@/components/buttons/Button";

// Offer Acceptance's dedicated Type B view (spec §13): shows the selected bank/amount
// and a single, explicit Confirm Acceptance action — deliberately separate from
// selecting the offer itself (CreditEvaluationBankOffers), so a case always passes
// through this checkpoint before continuing to Additional Documents.
export function OfferAcceptancePanel({
  bankName,
  approvedAmount,
  canConfirm,
  onConfirm,
}: {
  bankName: string | null;
  approvedAmount: number | null;
  canConfirm: boolean;
  onConfirm: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
        <div>
          <div className="text-xs text-text/50">Selected Bank</div>
          <div className="text-sm font-medium text-text">{bankName ?? "—"}</div>
        </div>
        <div>
          <div className="text-xs text-text/50">Approved Amount</div>
          <div className="text-sm font-medium text-text">{approvedAmount != null ? `₹${approvedAmount.toLocaleString("en-IN")}` : "—"}</div>
        </div>
      </div>
      {canConfirm ? (
        <Button size="sm" onClick={onConfirm}>
          Confirm Acceptance
        </Button>
      ) : (
        <p className="text-xs text-text/40">Awaiting confirmation.</p>
      )}
    </div>
  );
}
