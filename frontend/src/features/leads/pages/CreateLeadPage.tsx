import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { EligibleAssigneeSelect } from "@/components/forms/EligibleAssigneeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { TextareaField } from "@/components/forms/TextareaField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { checkDuplicate, createLead, getLeadLookup, SELF_SENTINEL } from "@/features/leads/api";
import { getErrorMessage } from "@/features/leads/errors";
import { ApiError } from "@/shared/api/client";
import { getFieldErrors } from "@/shared/api/errors";
import { getCurrentCoordinates } from "@/shared/geolocation";

interface LookupOption {
  id: string;
  name: string;
}

// Deliberately basic — an Employee taking a Create Lead call only ever knows Name/Mobile/
// Product/Source, never the customer's own business details (GST/turnover/etc). Those
// belong to the Dynamic Product Form the Customer fills in themselves after the Secure
// Link flow (see docs/decisions/DECISIONS.md) — this page no longer renders the Product
// Schema Engine's Basic Information fields at all.
//
// Source/Product dropdowns come from `getLeadLookup()` (`GET /leads/lookup`, gated on
// leads:leads:view) — a Leads-owned read, not a proxy through system_settings' own
// CRUD-gated lead-sources/loan-products/insurance-products endpoints. Fixed a real
// production bug: an employee with only leads:leads granted used to get "Missing
// permission: system_settings:lead_sources:view" trying to open this form.
export function CreateLeadPage() {
  const navigate = useNavigate();
  const [sources, setSources] = useState<LookupOption[]>([]);
  const [loanProducts, setLoanProducts] = useState<LookupOption[]>([]);
  const [insuranceProducts, setInsuranceProducts] = useState<LookupOption[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [productCategory, setProductCategory] = useState<"loan" | "insurance">("loan");
  const [productId, setProductId] = useState("");
  const [city, setCity] = useState("");
  const [preferredAmount, setPreferredAmount] = useState("");
  const [salaryInHand, setSalaryInHand] = useState("");
  const [nextFollowUpDate, setNextFollowUpDate] = useState("");
  // Seeds the lead's first Comment History entry (LeadNote) — distinct from the plain
  // `remarks` field this page never collected. See spec section 8/backend decision 125.
  const [comment, setComment] = useState("");
  // "" = leave unassigned (Fresh Leads), "self" = Assign To: Self, "employee" = pick from
  // EligibleAssigneeSelect — resolved server-side, see backend
  // LeadService._resolve_assignee (decision 125).
  const [assignTo, setAssignTo] = useState<"" | "self" | "employee">("");
  const [assigneeId, setAssigneeId] = useState("");

  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  // Set only when the backend actually BLOCKED creation (an active, non-rejected
  // duplicate already exists) — distinct from `duplicateWarning` above, which is a
  // non-blocking heads-up shown on blur for a mobile that only matches a REJECTED lead.
  const [duplicateBlocked, setDuplicateBlocked] = useState<{ leadId: string; leadCode: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    getLeadLookup()
      .then(({ sources: s, loan_products: lp, insurance_products: ip }) => {
        setSources(s);
        setLoanProducts(lp);
        setInsuranceProducts(ip);
        // Employees adding a lead directly aren't "sourcing" from anywhere —
        // default to Manual so the field needs no thought for the common case,
        // while staying editable for e.g. a phoned-in partner referral.
        const manual = s.find((source) => source.name.toLowerCase() === "manual");
        if (manual) setSourceId(manual.id);
      })
      .catch((err) => setLoadError(getErrorMessage(err)));
  }, []);

  useEffect(() => {
    setProductId("");
  }, [productCategory]);

  const onMobileBlur = async () => {
    if (!/^[6-9]\d{9}$/.test(mobile)) return;
    try {
      const { matches } = await checkDuplicate(mobile);
      setDuplicateWarning(matches.length > 0 ? `${matches.length} existing lead(s) already use this mobile number.` : null);
    } catch {
      setDuplicateWarning(null);
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setDuplicateBlocked(null);
    setIsSubmitting(true);
    try {
      // Best-effort — only checked server-side if a Geo Fence is configured for
      // lead_creation; a denied/unavailable browser permission just omits these and lets
      // the backend decide (see @/shared/geolocation).
      const coords = await getCurrentCoordinates();
      const lead = await createLead({
        full_name: fullName,
        mobile,
        email: email || undefined,
        source_id: sourceId,
        product_category: productCategory,
        product_id: productId,
        city: city || undefined,
        preferred_amount: preferredAmount ? Number(preferredAmount) : undefined,
        salary_in_hand: salaryInHand ? Number(salaryInHand) : undefined,
        next_follow_up_date: nextFollowUpDate || undefined,
        comment: comment || undefined,
        assigned_to: assignTo === "self" ? SELF_SENTINEL : assignTo === "employee" ? assigneeId || undefined : undefined,
        latitude: coords?.latitude,
        longitude: coords?.longitude,
      });
      navigate(`/leads/${lead.id}`);
    } catch (err) {
      // Production bug fix: creation is now blocked server-side when an active
      // (non-rejected) lead already exists for this mobile — surfaced distinctly, with
      // a direct link to the existing lead, rather than the generic error banner alone.
      if (err instanceof ApiError && err.code === "conflict") {
        const details = err.details as { existing_lead_id?: string; existing_lead_code?: string } | undefined;
        if (details?.existing_lead_id) {
          setDuplicateBlocked({ leadId: details.existing_lead_id, leadCode: details.existing_lead_code ?? "" });
        } else {
          setError(getErrorMessage(err));
        }
      } else {
        setError(getErrorMessage(err));
        setFieldErrors(getFieldErrors(err) ?? {});
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const products = productCategory === "loan" ? loanProducts : insuranceProducts;

  return (
    <SimplePageLayout title="Create Lead" backTo="/leads">
      <ErrorBanner message={loadError} />
      <ErrorBanner message={error} />
      {duplicateBlocked && (
        <div className="mb-4 rounded border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          Duplicate lead: a lead already exists with this mobile number
          {duplicateBlocked.leadCode ? ` (${duplicateBlocked.leadCode})` : ""}.{" "}
          <Link to={`/leads/${duplicateBlocked.leadId}`} className="font-semibold underline">
            Open existing lead
          </Link>
        </div>
      )}
      {duplicateWarning && (
        <div className="mb-4 rounded border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">{duplicateWarning}</div>
      )}

      <form onSubmit={onSubmit} noValidate className="max-w-4xl mx-auto bg-card border border-border rounded-card shadow-card p-6">
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <FormField
            label="Full Name"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            error={fieldErrors.full_name}
          />
          <FormField
            label="Mobile"
            required
            maxLength={10}
            value={mobile}
            onChange={(e) => setMobile(e.target.value)}
            onBlur={onMobileBlur}
            error={fieldErrors.mobile}
          />
          <FormField
            label="Email (optional)"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={fieldErrors.email}
          />

          <SelectField
            label="Lead Source"
            required
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
            placeholder="Select a source"
            options={sources.map((s) => ({ value: s.id, label: s.name }))}
          />

          <SelectField
            label="Product Category"
            value={productCategory}
            onChange={(e) => setProductCategory(e.target.value as "loan" | "insurance")}
            options={[
              { value: "loan", label: "Loan" },
              { value: "insurance", label: "Insurance" },
            ]}
          />

          <SelectField
            label="Product"
            required
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            placeholder="Select a product"
            options={products.map((p) => ({ value: p.id, label: p.name }))}
          />

          <FormField
            label="City (optional)"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            error={fieldErrors.city}
          />
          <FormField
            label="Preferred Loan Amount (optional)"
            type="number"
            min={1}
            value={preferredAmount}
            onChange={(e) => setPreferredAmount(e.target.value)}
            error={fieldErrors.preferred_amount}
          />
          <FormField
            label="Salary In Hand (optional)"
            type="number"
            min={1}
            value={salaryInHand}
            onChange={(e) => setSalaryInHand(e.target.value)}
            error={fieldErrors.salary_in_hand}
          />
          <FormField
            label="Next Follow Up Date (optional)"
            type="date"
            value={nextFollowUpDate}
            onChange={(e) => setNextFollowUpDate(e.target.value)}
            error={fieldErrors.next_follow_up_date}
          />
        </div>

        <TextareaField label="Comments (optional)" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />

        <div className="mb-4">
          <label className="block text-sm font-medium text-text mb-1.5">Assign To (optional)</label>
          <div className="flex gap-2">
            {(["", "self", "employee"] as const).map((option) => (
              <button
                key={option || "unassigned"}
                type="button"
                onClick={() => setAssignTo(option)}
                className={`flex-1 rounded-xl border py-2.5 text-sm font-semibold transition-colors ${
                  assignTo === option ? "border-primary bg-primary/10 text-primary" : "border-border text-textSecondary hover:bg-background"
                }`}
              >
                {option === "" ? "Leave Unassigned" : option === "self" ? "Self" : "Choose Employee"}
              </button>
            ))}
          </div>
          {assignTo === "employee" && (
            <div className="mt-3">
              <EligibleAssigneeSelect productCategory={productCategory} productId={productId} value={assigneeId} onChange={setAssigneeId} />
            </div>
          )}
        </div>

        <SubmitButton isSubmitting={isSubmitting}>Create Lead</SubmitButton>
      </form>
    </SimplePageLayout>
  );
}
