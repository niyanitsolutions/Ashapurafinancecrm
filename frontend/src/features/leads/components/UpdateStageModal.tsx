import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/badges/Badge";
import { Button } from "@/components/buttons/Button";
import { CheckboxField } from "@/components/forms/CheckboxField";
import { Modal } from "@/components/overlays/Modal";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { usePermissions } from "@/features/access_control/usePermissions";
import { RejectLeadModal } from "@/features/leads/components/RejectLeadModal";
import {
  createCustomerAccount,
  getLead,
  setLeadStage,
  updateFinancialAssessment,
  type LeadDetail,
  type LeadListItem,
} from "@/features/leads/api";
import { getErrorMessage } from "@/features/leads/errors";

const SALARY_MODE_OPTIONS = [
  { value: "account", label: "Account" },
  { value: "cash", label: "Cash" },
  { value: "cheque", label: "Cheque" },
] as const;

const LAST_3_MONTHS_OPTIONS = [
  { value: "same", label: "Same" },
  { value: "hiked", label: "Hiked" },
  { value: "decreased", label: "Decreased" },
  { value: "partial", label: "Partial" },
];

function ToggleGroup<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T | "";
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex gap-2">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`flex-1 rounded-xl border py-2 text-sm font-semibold transition-colors ${
            value === opt.value ? "border-primary bg-primary/10 text-primary" : "border-border text-textSecondary hover:bg-background"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// My Leads' "Update" action. Phase 1 shipped the Stage transition (My Leads <->
// Document Collection, spec section 16) and Reject (spec section 17) as a stub. Phase 2
// (decision 126) fills in the financial/customer assessment form (spec section 13) and
// Create Customer Account (spec section 14). Phase 3 (decision 127) adds the
// Application & Documents section and "Move to Loan Management" — both reuse the
// existing Application/ApplicationDocument entities read-only; the actual document
// Accept/Reject/Re-upload workflow lives entirely on the existing, unmodified
// `/applications/:id` page this section links out to.
export function UpdateStageModal({
  lead,
  onClose,
  onChanged,
}: {
  lead: LeadListItem;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { can } = usePermissions();
  const canReject = can("leads:leads", "reject");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isRejecting, setIsRejecting] = useState(false);

  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(true);

  // Financial Assessment form state (spec section 13).
  const [mockOffSalary, setMockOffSalary] = useState("");
  const [salaryMode, setSalaryMode] = useState<"account" | "cash" | "cheque" | "">("");
  const [emiRange, setEmiRange] = useState("");
  const [totalExperience, setTotalExperience] = useState("");
  const [currentCompanyExperience, setCurrentCompanyExperience] = useState("");
  const [companyLocation, setCompanyLocation] = useState("");
  const [anyLoan, setAnyLoan] = useState<"yes" | "no" | "">("");
  const [last3MonthsSalary, setLast3MonthsSalary] = useState<"same" | "hiked" | "decreased" | "partial" | "">("");
  const [cibilScore, setCibilScore] = useState("");
  const [cibilUnknown, setCibilUnknown] = useState(false);
  const [financialRemarks, setFinancialRemarks] = useState("");
  const [isSavingFinancial, setIsSavingFinancial] = useState(false);
  const [financialError, setFinancialError] = useState<string | null>(null);
  const [financialSaved, setFinancialSaved] = useState(false);

  // Create Customer Account form state (spec section 14).
  const [password, setPassword] = useState("");
  const [isCreatingAccount, setIsCreatingAccount] = useState(false);
  const [accountError, setAccountError] = useState<string | null>(null);

  useEffect(() => {
    getLead(lead.id)
      .then((l) => {
        setDetail(l);
        const fa = l.financial_assessment;
        setMockOffSalary(fa?.mock_off_salary != null ? String(fa.mock_off_salary) : "");
        setSalaryMode(fa?.salary_mode ?? "");
        setEmiRange(fa?.emi_range ?? "");
        setTotalExperience(fa?.total_experience ?? "");
        setCurrentCompanyExperience(fa?.current_company_experience ?? "");
        setCompanyLocation(fa?.company_location ?? "");
        setAnyLoan(fa?.any_loan == null ? "" : fa.any_loan ? "yes" : "no");
        setLast3MonthsSalary(fa?.last_3_months_salary ?? "");
        setCibilScore(fa?.cibil_score != null ? String(fa.cibil_score) : "");
        setCibilUnknown(fa?.cibil_unknown ?? false);
        setFinancialRemarks(fa?.remarks ?? "");
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoadingDetail(false));
  }, [lead.id]);

  const stage = detail?.stage ?? lead.stage;

  const moveStage = async (nextStage: "assigned" | "document_collection" | "loan_management") => {
    setError(null);
    setIsSubmitting(true);
    try {
      await setLeadStage(lead.id, nextStage);
      onChanged();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const onSaveFinancialAssessment = async () => {
    setFinancialError(null);
    setFinancialSaved(false);
    setIsSavingFinancial(true);
    try {
      const updated = await updateFinancialAssessment(lead.id, {
        mock_off_salary: mockOffSalary ? Number(mockOffSalary) : null,
        salary_mode: salaryMode || null,
        emi_range: emiRange || null,
        total_experience: totalExperience || null,
        current_company_experience: currentCompanyExperience || null,
        company_location: companyLocation || null,
        any_loan: anyLoan === "" ? null : anyLoan === "yes",
        last_3_months_salary: last3MonthsSalary || null,
        cibil_score: cibilUnknown || !cibilScore ? null : Number(cibilScore),
        cibil_unknown: cibilUnknown,
        remarks: financialRemarks || null,
      });
      setDetail(updated);
      setFinancialSaved(true);
      onChanged();
    } catch (err) {
      setFinancialError(getErrorMessage(err));
    } finally {
      setIsSavingFinancial(false);
    }
  };

  const onCreateAccount = async () => {
    if (!password) return;
    setAccountError(null);
    setIsCreatingAccount(true);
    try {
      const updated = await createCustomerAccount(lead.id, password);
      setDetail(updated);
      setPassword("");
      onChanged();
    } catch (err) {
      setAccountError(getErrorMessage(err));
    } finally {
      setIsCreatingAccount(false);
    }
  };

  if (isRejecting) {
    return (
      <RejectLeadModal
        leadId={lead.id}
        leadCode={lead.lead_code}
        onClose={() => setIsRejecting(false)}
        onRejected={() => {
          onChanged();
          onClose();
        }}
      />
    );
  }

  return (
    <Modal open onClose={onClose} size="lg" title="Update Lead" description={`Lead ${lead.lead_code}`}>
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}

      {isLoadingDetail ? (
        <p className="py-6 text-center text-sm text-textSecondary">Loading…</p>
      ) : (
        <div className="space-y-6">
          <section>
            <h3 className="mb-3 text-sm font-semibold text-text">Financial Assessment</h3>
            {financialError && <p className="mb-3 text-sm text-danger">{financialError}</p>}
            {financialSaved && <p className="mb-3 text-sm text-success">Financial details saved.</p>}

            <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">Mock Off Salary</label>
                <input
                  type="number"
                  min={0}
                  value={mockOffSalary}
                  onChange={(e) => setMockOffSalary(e.target.value)}
                  className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">EMI Range</label>
                <input
                  type="text"
                  value={emiRange}
                  onChange={(e) => setEmiRange(e.target.value)}
                  placeholder="e.g. 10000-15000"
                  className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">Total Experience</label>
                <input
                  type="text"
                  value={totalExperience}
                  onChange={(e) => setTotalExperience(e.target.value)}
                  placeholder="e.g. 5 Years"
                  className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">Current Company Experience</label>
                <input
                  type="text"
                  value={currentCompanyExperience}
                  onChange={(e) => setCurrentCompanyExperience(e.target.value)}
                  placeholder="e.g. 2 Years"
                  className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-sm font-medium text-text">Company Location</label>
                <input
                  type="text"
                  value={companyLocation}
                  onChange={(e) => setCompanyLocation(e.target.value)}
                  className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">Salary Mode</label>
                <ToggleGroup value={salaryMode} options={SALARY_MODE_OPTIONS} onChange={setSalaryMode} />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">Any Loan / Balance</label>
                <ToggleGroup
                  value={anyLoan}
                  options={
                    [
                      { value: "yes", label: "Yes" },
                      { value: "no", label: "No" },
                    ] as const
                  }
                  onChange={setAnyLoan}
                />
              </div>

              <SelectField
                label="Last 3 Months Salary"
                value={last3MonthsSalary}
                onChange={(e) => setLast3MonthsSalary(e.target.value as typeof last3MonthsSalary)}
                placeholder="Select"
                options={LAST_3_MONTHS_OPTIONS}
              />

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">CIBIL Score</label>
                <input
                  type="number"
                  min={300}
                  max={900}
                  disabled={cibilUnknown}
                  value={cibilUnknown ? "" : cibilScore}
                  onChange={(e) => setCibilScore(e.target.value)}
                  className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:bg-background disabled:text-text/40"
                />
                <div className="mt-1.5">
                  <CheckboxField
                    label="Don't Know"
                    checked={cibilUnknown}
                    onChange={(e) => {
                      setCibilUnknown(e.target.checked);
                      if (e.target.checked) setCibilScore("");
                    }}
                  />
                </div>
              </div>
            </div>

            <div className="mt-3">
              <TextareaField label="Remarks" rows={2} value={financialRemarks} onChange={(e) => setFinancialRemarks(e.target.value)} />
            </div>

            <Button size="sm" loading={isSavingFinancial} onClick={onSaveFinancialAssessment}>
              Save Financial Details
            </Button>
          </section>

          <section className="border-t border-border pt-5">
            <h3 className="mb-3 text-sm font-semibold text-text">Create Customer Account</h3>
            {detail?.account_created ? (
              <p className="text-sm text-success">Customer account already created.</p>
            ) : (
              <div className="space-y-3">
                {accountError && <p className="text-sm text-danger">{accountError}</p>}
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text">Phone Number</label>
                  <input
                    type="text"
                    disabled
                    value={lead.mobile}
                    className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm text-text/60"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text">Password</label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                </div>
                <Button size="sm" loading={isCreatingAccount} disabled={!password} onClick={onCreateAccount}>
                  Create Account
                </Button>
              </div>
            )}
          </section>

          {stage === "document_collection" && (
            <section className="border-t border-border pt-5">
              <h3 className="mb-3 text-sm font-semibold text-text">Application &amp; Documents</h3>
              {detail?.application_id ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-textSecondary">Status:</span>
                    {detail.application_status === "submitted" ? (
                      <StatusBadge status="submitted" label="Submitted" />
                    ) : (
                      <StatusBadge status="pending" label="Pending" />
                    )}
                  </div>
                  {detail.application_status === "submitted" && (
                    <p className="text-sm text-text">
                      {detail.documents_verified} of {detail.documents_required} required documents verified.
                    </p>
                  )}
                  <Link to={`/applications/${detail.application_id}`} className="inline-block text-sm font-medium text-primary hover:underline">
                    View Full Application →
                  </Link>
                </div>
              ) : (
                <p className="text-sm text-textSecondary">No application yet — use Generate Link to invite the customer.</p>
              )}
            </section>
          )}

          <section className="border-t border-border pt-5">
            <p className="mb-1 text-xs text-textSecondary">Current Stage</p>
            <p className="mb-3 text-sm font-semibold capitalize text-text">{stage.replace(/_/g, " ")}</p>

            <div className="space-y-2.5">
              {stage === "assigned" && (
                <Button className="w-full" loading={isSubmitting} onClick={() => moveStage("document_collection")}>
                  Move to Document Collection
                </Button>
              )}
              {stage === "document_collection" && (
                <Button className="w-full" loading={isSubmitting} onClick={() => moveStage("assigned")}>
                  Move back to My Leads
                </Button>
              )}
              {stage === "document_collection" && (
                <>
                  <Button
                    className="w-full"
                    loading={isSubmitting}
                    disabled={!detail?.all_documents_verified}
                    onClick={() => moveStage("loan_management")}
                  >
                    Move to Loan Management
                  </Button>
                  {!detail?.all_documents_verified && (
                    <p className="text-xs text-textSecondary">
                      {detail?.application_status !== "submitted"
                        ? "The customer must submit their application before this lead can move to Loan Management."
                        : `${detail?.documents_verified ?? 0} of ${detail?.documents_required ?? 0} required documents verified — all must be verified first.`}
                    </p>
                  )}
                </>
              )}
              {canReject && (
                <Button variant="danger" className="w-full" onClick={() => setIsRejecting(true)}>
                  Reject Lead
                </Button>
              )}
              <Button variant="secondary" className="w-full" onClick={onClose}>
                Close
              </Button>
            </div>
          </section>
        </div>
      )}
    </Modal>
  );
}
