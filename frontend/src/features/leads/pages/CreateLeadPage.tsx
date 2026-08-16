import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { TextareaField } from "@/components/forms/TextareaField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { checkDuplicate, createLead, getLeadLookup } from "@/features/leads/api";
import { getErrorMessage } from "@/features/leads/errors";
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
  const [remarks, setRemarks] = useState("");

  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
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
        remarks: remarks || undefined,
        latitude: coords?.latitude,
        longitude: coords?.longitude,
      });
      navigate(`/leads/${lead.id}`);
    } catch (err) {
      setError(getErrorMessage(err));
      setFieldErrors(getFieldErrors(err) ?? {});
    } finally {
      setIsSubmitting(false);
    }
  };

  const products = productCategory === "loan" ? loanProducts : insuranceProducts;

  return (
    <SimplePageLayout title="Create Lead" backTo="/leads">
      <ErrorBanner message={loadError} />
      <ErrorBanner message={error} />
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
        </div>

        <TextareaField label="Remarks (optional)" rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} />

        <SubmitButton isSubmitting={isSubmitting}>Create Lead</SubmitButton>
      </form>
    </SimplePageLayout>
  );
}
