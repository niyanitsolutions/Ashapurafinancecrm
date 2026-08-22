import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import {
  confirmOwnOfferAcceptance,
  getOwnLoanCase,
  listOwnBankOffers,
  listOwnLoanCases,
  selectOwnBankOffer,
  type CustomerBankOffer,
  type LoanCaseDetail,
} from "@/features/loan_management/api";

// Customer-facing bank/NBFC offer selection (spec §9-10, §13) — reached from Portal Home
// via the application id. Shows ONLY bank name + approved amount for Approved offers
// (never bank_application_id/assigned_officer/reference_number/remarks — trimmed at the
// backend, `CustomerBankOfferResponse`). Selecting an offer moves the case to Offer
// Acceptance but does NOT itself confirm acceptance — a separate, explicit Confirm
// Acceptance action is always required (decision #129).
export function LoanOffersPage() {
  const { id: applicationId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loanCase, setLoanCase] = useState<LoanCaseDetail | null>(null);
  const [offers, setOffers] = useState<CustomerBankOffer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirmOfferId, setConfirmOfferId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = () => {
    if (!applicationId) return;
    setError(null);
    listOwnLoanCases()
      .then(async (cases) => {
        const match = cases.find((c) => c.application_id === applicationId);
        if (!match) {
          setError("No loan case exists yet for this application.");
          setIsLoading(false);
          return;
        }
        const [detail, offerList] = await Promise.all([getOwnLoanCase(match.id), listOwnBankOffers(match.id)]);
        setLoanCase(detail);
        setOffers(offerList);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [applicationId]);

  const selectOffer = async (offerId: string) => {
    if (!loanCase) return;
    setError(null);
    try {
      await selectOwnBankOffer(loanCase.id, offerId);
      setConfirmOfferId(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const confirmAcceptance = async () => {
    if (!loanCase) return;
    setError(null);
    try {
      await confirmOwnOfferAcceptance(loanCase.id);
      navigate(`/portal/applications/${applicationId}/timeline`);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Available Loan Offers" backTo={applicationId ? `/portal/applications/${applicationId}/timeline` : "/portal"}>
      <ErrorBanner message={error} />

      {isLoading && <p className="text-sm text-text/40">Loading…</p>}

      {!isLoading && loanCase?.current_status === "offer_acceptance" && (
        <div className="mb-6 rounded-card border border-primary/30 bg-primary/5 p-5">
          <h3 className="text-sm font-semibold text-text mb-2">Your Selected Offer</h3>
          <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2 mb-4">
            <div>
              <div className="text-xs text-text/50">Bank</div>
              <div className="text-sm font-medium text-text">{loanCase.selected_bank_name ?? "—"}</div>
            </div>
            <div>
              <div className="text-xs text-text/50">Approved Amount</div>
              <div className="text-sm font-medium text-text">{loanCase.approved_amount != null ? `₹${loanCase.approved_amount.toLocaleString("en-IN")}` : "—"}</div>
            </div>
          </div>
          <Button onClick={confirmAcceptance}>Confirm Acceptance</Button>
        </div>
      )}

      {!isLoading && loanCase && loanCase.current_status === "credit_evaluation" && (
        <>
          {offers.length === 0 && <p className="text-sm text-text/40">No approved offers available yet. Check back soon.</p>}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {offers.map((offer) => (
              <div key={offer.id} className="rounded-card border border-border bg-card shadow-card p-5">
                <h3 className="text-base font-semibold text-text">{offer.bank_name}</h3>
                <div className="mt-3">
                  <div className="text-xs text-text/50">Approved Amount</div>
                  <div className="text-lg font-semibold text-text">₹{offer.approved_amount.toLocaleString("en-IN")}</div>
                </div>
                <Button className="mt-4 w-full" onClick={() => setConfirmOfferId(offer.id)}>
                  Select
                </Button>
              </div>
            ))}
          </div>
        </>
      )}

      {!isLoading && loanCase && !["credit_evaluation", "offer_acceptance"].includes(loanCase.current_status) && (
        <p className="text-sm text-text/40">No offer selection is available at this stage.</p>
      )}

      <ConfirmDialog
        open={confirmOfferId !== null}
        title="Select This Offer"
        message="Select this offer? Your case will move to Offer Acceptance, where you'll confirm acceptance in a separate step."
        confirmLabel="Select Offer"
        onConfirm={() => {
          if (confirmOfferId) return selectOffer(confirmOfferId);
        }}
        onClose={() => setConfirmOfferId(null)}
      />
    </SimplePageLayout>
  );
}
