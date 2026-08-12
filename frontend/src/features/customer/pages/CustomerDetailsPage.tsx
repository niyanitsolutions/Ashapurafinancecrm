import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getCustomerStaff, type Customer } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="text-xs text-text/50">{label}</div>
      <div className="text-sm">{value || "—"}</div>
    </div>
  );
}

export function CustomerDetailsPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!customerId) return;
    getCustomerStaff(customerId)
      .then(setCustomer)
      .catch((err) => setError(getErrorMessage(err)));
  }, [customerId]);

  if (!customerId) return null;
  if (error && !customer) {
    return (
      <SimplePageLayout title="Customer" backTo="/customers">
        <p className="text-sm text-danger">{error}</p>
      </SimplePageLayout>
    );
  }
  if (!customer) {
    return (
      <SimplePageLayout title="Customer" backTo="/customers">
        <p className="text-sm text-text/50">Loading…</p>
      </SimplePageLayout>
    );
  }

  return (
    <SimplePageLayout title={`${customer.full_name} (${customer.customer_code})`} backTo="/customers">
      <div className="max-w-2xl bg-card border border-border rounded-card shadow-card p-6 grid grid-cols-2 gap-x-4 gap-y-3">
        <Field label="Mobile" value={customer.mobile} />
        <Field label="Email" value={customer.email} />
        <Field label="Date of Birth" value={customer.date_of_birth} />
        <Field label="Gender" value={customer.gender} />
        <Field label="PAN" value={customer.pan_number_masked} />
        <Field label="Aadhaar" value={customer.aadhaar_number_masked} />
        <Field label="Status" value={customer.status} />
        <Field label="Converted from Lead" value={customer.converted_from_lead_id} />
        {customer.address && (
          <div className="col-span-2">
            <Field
              label="Address"
              value={[customer.address.line1, customer.address.line2, customer.address.city, customer.address.state, customer.address.pincode]
                .filter(Boolean)
                .join(", ")}
            />
          </div>
        )}
      </div>
    </SimplePageLayout>
  );
}
