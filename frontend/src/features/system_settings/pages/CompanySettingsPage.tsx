import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { CheckboxField } from "@/components/forms/CheckboxField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  type Address,
  type BusinessHour,
  type CompanySettings,
  confirmLogo,
  getCompanySettings,
  getLogoUploadUrl,
  updateCompanySettings,
  WEEKDAYS,
} from "@/features/system_settings/api";
import { getErrorMessage } from "@/features/system_settings/errors";

function defaultHours(): BusinessHour[] {
  return WEEKDAYS.map((day) => ({ day, is_closed: day === "sun", open_time: "10:00", close_time: "18:00" }));
}

const EMPTY_ADDRESS: Address = { line1: "", line2: "", city: "", state: "", pincode: "" };

// Primary/secondary color + logo are stored but not yet applied by the frontend at
// runtime — the app still uses its fixed Tailwind theme tokens (see
// docs/KNOWN_LIMITATIONS.md). This page only manages the settings record itself.
export function CompanySettingsPage() {
  const [settings, setSettings] = useState<CompanySettings | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [primaryColor, setPrimaryColor] = useState("");
  const [secondaryColor, setSecondaryColor] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [address, setAddress] = useState<Address>(EMPTY_ADDRESS);
  const [hours, setHours] = useState<BusinessHour[]>(defaultHours());
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);

  const load = () => {
    getCompanySettings()
      .then((s) => {
        setSettings(s);
        setCompanyName(s.company_name);
        setPrimaryColor(s.primary_color ?? "");
        setSecondaryColor(s.secondary_color ?? "");
        setContactEmail(s.contact_email ?? "");
        setContactPhone(s.contact_phone ?? "");
        setAddress(s.address ?? EMPTY_ADDRESS);
        setHours(s.business_hours.length > 0 ? s.business_hours : defaultHours());
      })
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

  const hasAddress = Object.values(address).some((v) => v && v.trim());

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const updated = await updateCompanySettings({
        company_name: companyName.trim(),
        primary_color: primaryColor.trim() || undefined,
        secondary_color: secondaryColor.trim() || undefined,
        contact_email: contactEmail.trim() || undefined,
        contact_phone: contactPhone.trim() || undefined,
        address: hasAddress
          ? {
              line1: address.line1.trim(),
              line2: address.line2?.trim() || undefined,
              city: address.city.trim(),
              state: address.state.trim(),
              pincode: address.pincode.trim(),
            }
          : undefined,
        business_hours: hours,
      });
      setSettings(updated);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const onUploadLogo = async () => {
    if (!logoFile) return;
    setError(null);
    setIsUploadingLogo(true);
    try {
      const { upload_url, s3_key } = await getLogoUploadUrl();
      await fetch(upload_url, { method: "PUT", body: logoFile, headers: { "Content-Type": logoFile.type || "image/png" } });
      const updated = await confirmLogo(s3_key);
      setSettings(updated);
      setLogoFile(null);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsUploadingLogo(false);
    }
  };

  const updateHour = (day: string, patch: Partial<BusinessHour>) => {
    setHours((prev) => prev.map((h) => (h.day === day ? { ...h, ...patch } : h)));
  };

  if (!settings) {
    return (
      <SimplePageLayout title="Company Settings">
        <ErrorBanner message={error} />
      </SimplePageLayout>
    );
  }

  return (
    <SimplePageLayout title="Company Settings" subtitle="Manage company profile and business hours.">
      <ErrorBanner message={error} />

      <form onSubmit={onSave} className="max-w-2xl space-y-6">
        <div className="bg-card border border-border rounded-card shadow-card p-6">
          <FormField label="Company Name" value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
          <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <FormField label="Contact Email" type="email" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} />
            <FormField label="Contact Phone" value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} />
          </div>
          <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <FormField label="Primary Color" value={primaryColor} onChange={(e) => setPrimaryColor(e.target.value)} placeholder="#FF7A00" />
            <FormField label="Secondary Color" value={secondaryColor} onChange={(e) => setSecondaryColor(e.target.value)} placeholder="#FF9A3D" />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-text mb-1">Logo</label>
            {settings.logo_s3_key && <p className="text-sm text-text/60 mb-2">Current: {settings.logo_s3_key}</p>}
            <div className="flex items-center gap-3">
              <input type="file" accept="image/*" onChange={(e) => setLogoFile(e.target.files?.[0] ?? null)} />
              <Button variant="secondary" size="sm" disabled={!logoFile || isUploadingLogo} onClick={onUploadLogo}>
                {isUploadingLogo ? "Uploading…" : "Upload"}
              </Button>
            </div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-card shadow-card p-6">
          <h2 className="text-sm font-semibold text-text mb-3">Registered Address</h2>
          <FormField label="Address Line 1" value={address.line1} onChange={(e) => setAddress((a) => ({ ...a, line1: e.target.value }))} />
          <FormField label="Address Line 2" value={address.line2 ?? ""} onChange={(e) => setAddress((a) => ({ ...a, line2: e.target.value }))} />
          <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-3">
            <FormField label="City" value={address.city} onChange={(e) => setAddress((a) => ({ ...a, city: e.target.value }))} />
            <FormField label="State" value={address.state} onChange={(e) => setAddress((a) => ({ ...a, state: e.target.value }))} />
            <FormField label="Pincode" value={address.pincode} onChange={(e) => setAddress((a) => ({ ...a, pincode: e.target.value }))} />
          </div>
        </div>

        <div className="bg-card border border-border rounded-card shadow-card p-6">
          <h2 className="text-sm font-semibold text-text mb-3">Business Hours</h2>
          <div className="space-y-2">
            {hours.map((h) => (
              <div key={h.day} className="flex items-center gap-3 text-sm">
                <span className="w-10 uppercase text-text/60">{h.day}</span>
                <CheckboxField label="Closed" checked={h.is_closed} onChange={(e) => updateHour(h.day, { is_closed: e.target.checked })} />
                {!h.is_closed && (
                  <>
                    <input
                      type="time"
                      className="rounded border border-border px-2 py-1"
                      value={h.open_time ?? ""}
                      onChange={(e) => updateHour(h.day, { open_time: e.target.value })}
                    />
                    <span>to</span>
                    <input
                      type="time"
                      className="rounded border border-border px-2 py-1"
                      value={h.close_time ?? ""}
                      onChange={(e) => updateHour(h.day, { close_time: e.target.value })}
                    />
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        <SubmitButton isSubmitting={isSubmitting}>Save Company Settings</SubmitButton>
      </form>
    </SimplePageLayout>
  );
}
