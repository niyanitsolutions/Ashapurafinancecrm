import { useEffect, useState } from "react";
import { validateFormData } from "@/components/forms/fieldValidation";
import { ProductSchemaForm } from "@/components/forms/ProductSchemaForm";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { getErrorMessage } from "@/features/customer/errors";
import { useProductSchema } from "@/features/customer/useProductSchema";
import {
  addReferralLead,
  listOwnAddLeadProducts,
  listOwnLeads,
  updateReferralLead,
  type ReferralLead,
  type ReferralProductOption,
} from "@/features/referral_partner_management/api";

const PAGE_SIZE = 20;

export function ReferralPartnerLeadsPage() {
  const [items, setItems] = useState<ReferralLead[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [editingLeadId, setEditingLeadId] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    listOwnLeads({ page, page_size: PAGE_SIZE })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const run = async (action: () => Promise<unknown>, successMessage: string) => {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(successMessage);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <div>
      <h1 className="text-xl font-semibold text-text mb-6">My Leads</h1>
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
        <h3 className="text-sm font-semibold text-text/70 mb-3">Add Lead</h3>
        <AddLeadForm onSubmit={(payload) => run(() => addReferralLead(payload), "Lead submitted.")} />
      </div>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Code</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Mobile</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan={5} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>}
            {!isLoading && items.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-text/50">No leads submitted yet.</td></tr>}
            {items.map((lead) => (
              <tr key={lead.lead_id} className="border-b border-border last:border-0 hover:bg-background align-top">
                <td className="px-4 py-3">{lead.lead_code}</td>
                <td className="px-4 py-3">
                  {editingLeadId === lead.lead_id ? (
                    <EditLeadForm
                      lead={lead}
                      onCancel={() => setEditingLeadId(null)}
                      onSubmit={(payload) =>
                        run(() => updateReferralLead(lead.lead_id, payload), "Lead updated.").finally(() => setEditingLeadId(null))
                      }
                    />
                  ) : (
                    lead.full_name
                  )}
                </td>
                <td className="px-4 py-3">{lead.mobile}</td>
                <td className="px-4 py-3 capitalize">{lead.external_status.replace("_", " ")}</td>
                <td className="px-4 py-3">
                  {lead.editable && editingLeadId !== lead.lead_id && (
                    <button type="button" onClick={() => setEditingLeadId(lead.lead_id)} className="text-primary hover:underline text-xs">
                      Edit
                    </button>
                  )}
                  {!lead.editable && <span className="text-xs text-text/40">Locked — processing started</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} leads)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
}

function AddLeadForm({
  onSubmit,
}: {
  onSubmit: (payload: {
    full_name: string;
    mobile: string;
    email?: string;
    product_category: string;
    product_id: string;
    remarks?: string;
    product_form_data?: Record<string, unknown>;
  }) => void;
}) {
  const [fullName, setFullName] = useState("");
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [productCategory, setProductCategory] = useState<"loan" | "insurance">("loan");
  const [products, setProducts] = useState<ReferralProductOption[]>([]);
  const [productId, setProductId] = useState("");
  const [remarks, setRemarks] = useState("");
  const [productFormData, setProductFormData] = useState<Record<string, unknown>>({});
  const [productFieldErrors, setProductFieldErrors] = useState<Record<string, string>>({});
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    setProductId("");
    listOwnAddLeadProducts(productCategory)
      .then(setProducts)
      .catch(() => setProducts([]));
  }, [productCategory]);

  useEffect(() => {
    setProductFormData({});
    setProductFieldErrors({});
  }, [productId]);

  // Same Product Schema Engine every portal reads — a Referral Partner sees exactly the
  // same Basic Information fields for a product as Employee Create Lead / the Customer
  // Application form.
  const { data: productSchema } = useProductSchema(productId ? productCategory : undefined, productId || undefined);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setValidationError(null);
        if (productSchema && productSchema.fields.length > 0) {
          const errors = validateFormData(productSchema.fields, productFormData);
          if (Object.keys(errors).length > 0) {
            setProductFieldErrors(errors);
            setValidationError("Please fix the highlighted fields before submitting.");
            return;
          }
        }
        onSubmit({
          full_name: fullName,
          mobile,
          email: email || undefined,
          product_category: productCategory,
          product_id: productId,
          remarks: remarks || undefined,
          product_form_data: productSchema && productSchema.fields.length > 0 ? productFormData : undefined,
        });
        setFullName("");
        setMobile("");
        setEmail("");
        setProductId("");
        setRemarks("");
        setProductFormData({});
      }}
    >
      {validationError && <p className="mb-3 text-sm text-danger">{validationError}</p>}
      <div className="grid grid-cols-3 gap-3">
        <input placeholder="Full Name" value={fullName} onChange={(e) => setFullName(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
        <input placeholder="Mobile" value={mobile} onChange={(e) => setMobile(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
        <input placeholder="Email (optional)" value={email} onChange={(e) => setEmail(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
        <select
          value={productCategory}
          onChange={(e) => setProductCategory(e.target.value as "loan" | "insurance")}
          className="rounded border border-border px-3 py-2 text-sm"
        >
          <option value="loan">Loan</option>
          <option value="insurance">Insurance</option>
        </select>
        <select value={productId} onChange={(e) => setProductId(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required>
          <option value="">Select a product</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <input placeholder="Remarks (optional)" value={remarks} onChange={(e) => setRemarks(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
      </div>

      {productSchema && productSchema.fields.length > 0 && (
        <div className="mt-4 border-t border-border pt-4">
          <ProductSchemaForm
            fields={productSchema.fields}
            values={productFormData}
            onChange={(key, value) => {
              setProductFormData((prev) => ({ ...prev, [key]: value }));
              setProductFieldErrors((prev) => {
                if (!prev[key]) return prev;
                const { [key]: _removed, ...rest } = prev;
                return rest;
              });
            }}
            errors={productFieldErrors}
          />
        </div>
      )}

      <div className="mt-4">
        <SubmitButton>Add Lead</SubmitButton>
      </div>
    </form>
  );
}

function EditLeadForm({
  lead, onSubmit, onCancel,
}: {
  lead: ReferralLead;
  onSubmit: (payload: { full_name?: string; mobile?: string; email?: string; remarks?: string }) => void;
  onCancel: () => void;
}) {
  const [fullName, setFullName] = useState(lead.full_name);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ full_name: fullName });
      }}
      className="flex items-center gap-2"
    >
      <input value={fullName} onChange={(e) => setFullName(e.target.value)} className="rounded border border-border px-2 py-1 text-sm" />
      <button type="submit" className="text-primary hover:underline text-xs">Save</button>
      <button type="button" onClick={onCancel} className="text-text/50 hover:underline text-xs">Cancel</button>
    </form>
  );
}
