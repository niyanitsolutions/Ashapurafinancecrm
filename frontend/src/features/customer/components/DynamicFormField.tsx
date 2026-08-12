import { useQuery } from "@tanstack/react-query";
import { normalizeFieldValue } from "@/components/forms/fieldValidation";
import type { FormField } from "@/features/customer/api";
import { apiRequest } from "@/shared/api/client";

// Phase 3.1 — API-sourced dropdown options (reserved capability: states/cities/branches
// don't have a real endpoint yet, but the renderer is already wired for one — a schema
// field just needs `options_source: "api"` + `options_endpoint` set, no component
// change needed when a real endpoint shows up).
function useApiOptions(endpoint: string | null | undefined, enabled: boolean) {
  return useQuery<string[]>({
    queryKey: ["field-options", endpoint],
    queryFn: () => apiRequest<string[]>(endpoint as string),
    enabled: enabled && Boolean(endpoint),
    staleTime: 5 * 60_000,
  });
}

export function DynamicFormField({
  field,
  value,
  onChange,
  error,
}: {
  field: FormField;
  value: unknown;
  onChange: (key: string, value: unknown) => void;
  error?: string | null;
}) {
  const isApiSelect = field.field_type === "select" && field.options_source === "api";
  const { data: apiOptions, isLoading: isLoadingOptions } = useApiOptions(field.options_endpoint, isApiSelect);
  const options = isApiSelect ? apiOptions ?? [] : field.options ?? [];

  const commonProps = {
    id: field.key,
    required: field.required,
  };
  // Governance round — `placeholder` is now a real, Owner-editable schema field; the
  // label-derived fallback (Phase 3.1) still applies when the Owner hasn't set one.
  const placeholder =
    field.field_type === "select" ? undefined : field.placeholder || `Enter ${field.label.replace(/\s*\(.*?\)\s*/g, "").trim()}`;
  // Governance round — `trim`/`auto_uppercase` applied live as the Owner (Preview) or
  // Customer (real form) types, mirroring the backend's own normalization on save.
  const handleTextChange = (raw: string) => onChange(field.key, normalizeFieldValue(field, raw));

  return (
    <div className={`mb-4 ${field.field_type === "textarea" ? "md:col-span-2" : ""}`}>
      <label htmlFor={field.key} className="block text-sm font-medium text-text mb-1">
        {field.label}
        {field.required && <span className="text-danger"> *</span>}
      </label>
      {field.field_type === "select" ? (
        <select
          {...commonProps}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(field.key, e.target.value)}
          disabled={isApiSelect && isLoadingOptions}
          className="w-full rounded border border-border px-3 py-2 text-sm"
        >
          <option value="">{isApiSelect && isLoadingOptions ? "Loading…" : "Select…"}</option>
          {options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : field.field_type === "textarea" ? (
        <textarea
          {...commonProps}
          placeholder={placeholder}
          value={(value as string) ?? ""}
          onChange={(e) => handleTextChange(e.target.value)}
          className="w-full rounded border border-border px-3 py-2 text-sm"
          rows={3}
        />
      ) : field.field_type === "checkbox" ? (
        <input
          {...commonProps}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(field.key, e.target.checked)}
          className="rounded border border-border"
        />
      ) : (
        <input
          {...commonProps}
          type={field.field_type === "number" ? "number" : field.field_type === "date" ? "date" : "text"}
          placeholder={field.field_type === "date" ? undefined : placeholder}
          title={field.validation?.mask ? `Format: ${field.validation.mask}` : undefined}
          value={(value as string | number) ?? ""}
          onChange={(e) => (field.field_type === "number" ? onChange(field.key, Number(e.target.value)) : handleTextChange(e.target.value))}
          className="w-full rounded border border-border px-3 py-2 text-sm"
        />
      )}
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
