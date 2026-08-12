import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { getOwnCustomerProfile, updateOwnProfile, type Address, type Customer } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";

const GENDER_OPTIONS = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
  { value: "other", label: "Other" },
];

const EMPTY_ADDRESS: Address = { line1: "", line2: "", city: "", state: "", pincode: "", country: "India" };

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-6 mb-6">
      <h2 className="text-sm font-semibold text-text/70 mb-3">{title}</h2>
      {children}
    </div>
  );
}

export function ProfilePage() {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [gender, setGender] = useState("");
  const [address, setAddress] = useState<Address>(EMPTY_ADDRESS);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = () => {
    setError(null);
    getOwnCustomerProfile()
      .then((c) => {
        setCustomer(c);
        if (c) {
          setFullName(c.full_name);
          setEmail(c.email ?? "");
          setDateOfBirth(c.date_of_birth?.slice(0, 10) ?? "");
          setGender(c.gender ?? "");
          setAddress(c.address ?? EMPTY_ADDRESS);
        }
      })
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

  if (error && !customer) {
    return (
      <SimplePageLayout title="My Profile" backTo="/portal">
        <ErrorBanner message={error} />
        <button type="button" onClick={load} className="text-sm font-medium text-primary hover:underline">
          Try Again
        </button>
      </SimplePageLayout>
    );
  }
  if (!customer) {
    return (
      <SimplePageLayout title="My Profile" backTo="/portal">
        <div className="max-w-2xl space-y-4">
          {[0, 1].map((i) => (
            <div key={i} className="animate-shimmer h-40 rounded-card bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%]" />
          ))}
        </div>
      </SimplePageLayout>
    );
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setIsSubmitting(true);
    try {
      const hasAddress = Object.values(address).some((v) => (v ?? "").toString().trim() !== "");
      const updated = await updateOwnProfile({
        full_name: fullName,
        email: email || undefined,
        date_of_birth: dateOfBirth || undefined,
        gender: gender || undefined,
        address: hasAddress ? address : undefined,
      });
      setCustomer(updated);
      setMessage("Profile updated.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SimplePageLayout
      title="My Profile"
      subtitle={customer.customer_code}
      backTo="/portal"
      actions={
        <Link to="/portal/profile/sessions" className="text-sm text-primary hover:underline">
          Active Sessions
        </Link>
      }
    >
      <form onSubmit={onSubmit} noValidate className="max-w-2xl">
        <ErrorBanner message={error} />
        {message && <p className="mb-4 text-sm text-success">{message}</p>}

        <Section title="Personal Information">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6">
            <FormField label="Full Name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            <FormField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <FormField label="Date of Birth" type="date" value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} />
            <SelectField label="Gender" placeholder="Select" value={gender} onChange={(e) => setGender(e.target.value)} options={GENDER_OPTIONS} />
          </div>
        </Section>

        <Section title="Address">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6">
            <div className="md:col-span-2">
              <FormField label="Address Line 1" value={address.line1} onChange={(e) => setAddress((a) => ({ ...a, line1: e.target.value }))} />
            </div>
            <div className="md:col-span-2">
              <FormField label="Address Line 2 (optional)" value={address.line2 ?? ""} onChange={(e) => setAddress((a) => ({ ...a, line2: e.target.value }))} />
            </div>
            <FormField label="City" value={address.city} onChange={(e) => setAddress((a) => ({ ...a, city: e.target.value }))} />
            <FormField label="State" value={address.state} onChange={(e) => setAddress((a) => ({ ...a, state: e.target.value }))} />
            <FormField label="PIN Code" value={address.pincode} onChange={(e) => setAddress((a) => ({ ...a, pincode: e.target.value }))} />
          </div>
        </Section>

        <Section title="Identity Documents">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6">
            <FormField label="Mobile" value={customer.mobile} disabled />
            <FormField label="PAN" value={customer.pan_number_masked ?? "Not on file"} disabled />
            <FormField label="Aadhaar" value={customer.aadhaar_number_masked ?? "Not on file"} disabled />
          </div>
        </Section>

        <Section title="Account">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 text-sm">
            <div className="mb-4">
              <div className="text-text/50 text-xs mb-1">Customer Code</div>
              <div className="text-text">{customer.customer_code}</div>
            </div>
            <div className="mb-4">
              <div className="text-text/50 text-xs mb-1">Member Since</div>
              <div className="text-text">{new Date(customer.created_at).toLocaleDateString()}</div>
            </div>
          </div>
        </Section>

        <SubmitButton isSubmitting={isSubmitting}>Save Changes</SubmitButton>
      </form>
    </SimplePageLayout>
  );
}
