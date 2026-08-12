import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { ProductSchemaForm } from "@/components/forms/ProductSchemaForm";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  createProductSchemaVersion,
  freezeProductSchema,
  getProductSchema,
  getProductSchemaAudit,
  publishProductSchema,
  updateProductSchema,
  type FieldCondition,
  type FieldValidation,
  type FormDefinition,
  type FormField,
  type RequiredDocument,
  type SchemaAuditEntry,
} from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { Icon } from "@/theme/icons";

// Governance round — the Owner-facing schema editor (replaces the read-only table's
// dead end). Field/document lists are edited as a whole local copy and saved via the
// existing "full replace" PATCH, matching the UX the endpoint was already built for —
// the *server* is what enforces the master/custom permission split (see
// `CustomerService.update_form_definition`'s diff-by-key merge), this page just
// presents it: a locked Key/Type on a master field, a "Master" badge, and a rejection
// message surfaced through the normal error banner when the server says no.

const FIELD_TYPES: FormField["field_type"][] = ["text", "number", "date", "select", "textarea", "checkbox"];
const FORMATS = ["", "email", "mobile", "pan", "aadhaar", "ifsc", "gst", "pincode"] as const;
const OPERATORS: FieldCondition["operator"][] = ["equals", "not_equals", "in"];

const CHECKLIST_ITEMS = [
  "Fields verified", "Field order verified", "Labels verified", "Validation verified",
  "Required/Optional verified", "Conditional logic verified", "Documents verified", "Upload verified",
  "Database verified", "Customer Portal verified", "Employee Flow verified", "Owner Configuration verified",
  "Mobile Responsive verified", "Version Frozen",
];

type Tab = "fields" | "documents" | "preview" | "history";

function emptyField(): FormField {
  return { key: "", label: "", field_type: "text", required: false, options: null, section: null };
}

function emptyDocument(): RequiredDocument {
  return { document_type_id: "", document_type_name: "New Document", section: null, note: null, required: true };
}

function toInputField(f: FormField) {
  return {
    key: f.key, label: f.label, field_type: f.field_type, required: f.required, options: f.options, section: f.section,
    visible_when: f.visible_when, validation: f.validation, options_source: f.options_source, options_endpoint: f.options_endpoint,
    placeholder: f.placeholder, hidden: f.hidden,
  };
}

function toInputDocument(d: RequiredDocument) {
  return {
    document_type_id: d.document_type_id, section: d.section, note: d.note, name_override: d.name_override,
    required: d.required, allowed_types: d.allowed_types, max_size_mb: d.max_size_mb, multiple_upload: d.multiple_upload,
    preview_enabled: d.preview_enabled, hidden: d.hidden,
  };
}

export function SchemaEditorPage() {
  const { schemaId } = useParams<{ schemaId: string }>();
  const navigate = useNavigate();
  const [formDef, setFormDef] = useState<FormDefinition | null>(null);
  const [fields, setFields] = useState<FormField[]>([]);
  const [documents, setDocuments] = useState<RequiredDocument[]>([]);
  const [tab, setTab] = useState<Tab>("fields");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [showFreezeModal, setShowFreezeModal] = useState(false);
  const [checkedItems, setCheckedItems] = useState<Set<string>>(new Set());
  const [auditEntries, setAuditEntries] = useState<SchemaAuditEntry[] | null>(null);
  const [previewValues, setPreviewValues] = useState<Record<string, unknown>>({});

  const load = () => {
    if (!schemaId) return;
    setError(null);
    getProductSchema(schemaId)
      .then((def) => {
        setFormDef(def);
        setFields(def.fields);
        setDocuments(def.required_documents);
      })
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [schemaId]);

  useEffect(() => {
    if (tab === "history" && formDef && auditEntries === null) {
      getProductSchemaAudit(formDef.product_category, formDef.product_id)
        .then(setAuditEntries)
        .catch((err) => setError(getErrorMessage(err)));
    }
  }, [tab, formDef, auditEntries]);

  const isLocked = formDef?.is_locked ?? false;
  const isDraft = formDef?.status === "draft";

  if (error && !formDef) {
    return (
      <SimplePageLayout title="Edit Product Schema" backTo="/settings/product-schemas">
        <ErrorBanner message={error} />
      </SimplePageLayout>
    );
  }
  if (!formDef) {
    return (
      <SimplePageLayout title="Edit Product Schema" backTo="/settings/product-schemas">
        <div className="animate-shimmer h-40 rounded-card bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%]" />
      </SimplePageLayout>
    );
  }

  const runAction = async (action: () => Promise<FormDefinition>, successMessage: string) => {
    setIsBusy(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await action();
      setFormDef(updated);
      setFields(updated.fields);
      setDocuments(updated.required_documents);
      setMessage(successMessage);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  };

  const onSave = async () => {
    setIsSaving(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await updateProductSchema(formDef.id, {
        fields: fields.map(toInputField),
        required_documents: documents.map(toInputDocument),
      });
      setFormDef(updated);
      setFields(updated.fields);
      setDocuments(updated.required_documents);
      setAuditEntries(null);
      setMessage("Saved.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const onFreeze = () => {
    runAction(() => freezeProductSchema(formDef.id, [...checkedItems]), `Frozen as Version ${formDef.schema_version}.`).then(() => {
      setShowFreezeModal(false);
      setCheckedItems(new Set());
    });
  };

  const onNewVersion = () => {
    runAction(async () => {
      const draft = await createProductSchemaVersion(formDef.id);
      navigate(`/settings/product-schemas/${draft.id}`);
      return draft;
    }, "New draft version created.");
  };

  const onPublish = () => runAction(() => publishProductSchema(formDef.id), "Published — now live for customers.");

  return (
    <SimplePageLayout
      title={formDef.product_name || formDef.product_id}
      subtitle={`${formDef.product_category === "loan" ? "Loan" : "Insurance"} · Version ${formDef.schema_version}${isLocked ? " · Frozen (Read Only)" : ""}${isDraft ? " · Draft" : ""}`}
      backTo="/settings/product-schemas"
      actions={
        <>
          <button
            type="button"
            onClick={() => navigate(`/settings/product-schemas/compare?product_category=${formDef.product_category}&product_id=${formDef.product_id}`)}
            className="rounded-xl border border-border px-3.5 py-2 text-sm font-medium text-text/70 hover:bg-background"
          >
            Compare
          </button>
          {!isLocked && (
            <button
              type="button"
              disabled={isBusy}
              onClick={() => setShowFreezeModal(true)}
              className="rounded-xl border border-border px-3.5 py-2 text-sm font-medium text-text/70 hover:bg-background disabled:opacity-50"
            >
              Freeze
            </button>
          )}
          {isLocked && (
            <button
              type="button"
              disabled={isBusy}
              onClick={onNewVersion}
              className="rounded-xl border border-border px-3.5 py-2 text-sm font-medium text-text/70 hover:bg-background disabled:opacity-50"
            >
              New Version
            </button>
          )}
          {isDraft && (
            <button
              type="button"
              disabled={isBusy}
              onClick={onPublish}
              className="rounded-xl border border-success/30 bg-success/10 px-3.5 py-2 text-sm font-medium text-success hover:bg-success/20 disabled:opacity-50"
            >
              Publish
            </button>
          )}
          {!isLocked && (
            <button
              type="button"
              disabled={isSaving}
              onClick={onSave}
              className="hover-lift rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-2 px-4 shadow-card disabled:opacity-50"
            >
              {isSaving ? "Saving…" : "Save"}
            </button>
          )}
        </>
      }
    >
      <ErrorBanner message={error} />
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {isLocked && (
        <div className="mb-4 rounded-xl border border-text/10 bg-text/5 px-3.5 py-2.5 text-sm text-text/70">
          This schema version is frozen and read-only. Use "New Version" to make changes.
        </div>
      )}

      <div className="mb-4 flex gap-1 border-b border-border">
        {(["fields", "documents", "preview", "history"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize border-b-2 -mb-px ${
              tab === t ? "border-primary text-primary" : "border-transparent text-text/50 hover:text-text"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "fields" && (
        <FieldsTab fields={fields} setFields={setFields} disabled={isLocked} />
      )}
      {tab === "documents" && (
        <DocumentsTab documents={documents} setDocuments={setDocuments} disabled={isLocked} />
      )}
      {tab === "preview" && (
        <div className="bg-card border border-border rounded-card shadow-card p-6 max-w-3xl">
          <p className="mb-4 text-xs text-text/50">
            This is exactly what the customer will see — live, without saving. Fill it in to test conditional fields.
          </p>
          <ProductSchemaForm fields={fields} values={previewValues} onChange={(key, value) => setPreviewValues((v) => ({ ...v, [key]: value }))} />
        </div>
      )}
      {tab === "history" && <HistoryTab entries={auditEntries} />}

      {showFreezeModal && (
        <FreezeChecklistModal
          checkedItems={checkedItems}
          setCheckedItems={setCheckedItems}
          onCancel={() => setShowFreezeModal(false)}
          onConfirm={onFreeze}
          isBusy={isBusy}
        />
      )}
    </SimplePageLayout>
  );
}

function MasterBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
      <Icon name="shield-check" className="h-3 w-3" />
      Master
    </span>
  );
}

function FieldsTab({
  fields,
  setFields,
  disabled,
}: {
  fields: FormField[];
  setFields: (fields: FormField[]) => void;
  disabled: boolean;
}) {
  const update = (index: number, patch: Partial<FormField>) => {
    setFields(fields.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  };
  const remove = (index: number) => setFields(fields.filter((_, i) => i !== index));
  const move = (index: number, dir: -1 | 1) => {
    const target = index + dir;
    if (target < 0 || target >= fields.length) return;
    const next = [...fields];
    [next[index], next[target]] = [next[target], next[index]];
    setFields(next);
  };

  return (
    <div className="space-y-3 max-w-4xl">
      {fields.map((field, index) => {
        const isMaster = field.source === "master";
        return (
          <div key={index} className="bg-card border border-border rounded-card shadow-card p-4">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div className="flex items-center gap-2">
                {isMaster && <MasterBadge />}
                <code className="text-xs text-text/40">{field.key || "(new field — set a key below)"}</code>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button type="button" disabled={disabled} onClick={() => move(index, -1)} className="text-text/40 hover:text-text disabled:opacity-30">
                  <Icon name="chevron-left" className="h-4 w-4 rotate-90" />
                </button>
                <button type="button" disabled={disabled} onClick={() => move(index, 1)} className="text-text/40 hover:text-text disabled:opacity-30">
                  <Icon name="chevron-right" className="h-4 w-4 rotate-90" />
                </button>
                {!isMaster && (
                  <button type="button" disabled={disabled} onClick={() => remove(index)} className="ml-2 text-xs text-danger hover:underline disabled:opacity-30">
                    Delete
                  </button>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
              {!isMaster && (
                <label className="text-xs text-text/60">
                  Key (permanent, cannot change once saved)
                  <input
                    value={field.key}
                    disabled={disabled}
                    onChange={(e) => update(index, { key: e.target.value.trim() })}
                    className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                  />
                </label>
              )}
              <label className="text-xs text-text/60">
                Label
                <input
                  value={field.label}
                  disabled={disabled}
                  onChange={(e) => update(index, { label: e.target.value })}
                  className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                />
              </label>
              <label className="text-xs text-text/60">
                Placeholder
                <input
                  value={field.placeholder ?? ""}
                  disabled={disabled}
                  onChange={(e) => update(index, { placeholder: e.target.value || null })}
                  className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                />
              </label>
              <label className="text-xs text-text/60">
                Type {isMaster && <span className="text-text/30">(locked — master field)</span>}
                <select
                  value={field.field_type}
                  disabled={disabled || isMaster}
                  onChange={(e) => update(index, { field_type: e.target.value as FormField["field_type"] })}
                  className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm bg-card disabled:bg-background disabled:text-text/40"
                >
                  {FIELD_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-text/60">
                Section
                <input
                  value={field.section ?? ""}
                  disabled={disabled}
                  onChange={(e) => update(index, { section: e.target.value || null })}
                  className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                />
              </label>
              {field.field_type === "select" && (
                <label className="text-xs text-text/60">
                  Options (comma-separated)
                  <input
                    value={(field.options ?? []).join(", ")}
                    disabled={disabled}
                    onChange={(e) => update(index, { options: e.target.value.split(",").map((o) => o.trim()).filter(Boolean) })}
                    className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                  />
                </label>
              )}
            </div>

            <div className="flex items-center gap-4 mb-3">
              <label className="flex items-center gap-1.5 text-xs text-text/70">
                <input type="checkbox" checked={field.required} disabled={disabled} onChange={(e) => update(index, { required: e.target.checked })} />
                Required
              </label>
              <label className="flex items-center gap-1.5 text-xs text-text/70">
                <input type="checkbox" checked={field.hidden ?? false} disabled={disabled} onChange={(e) => update(index, { hidden: e.target.checked })} />
                Hidden
              </label>
            </div>

            <details className="text-xs">
              <summary className="cursor-pointer text-text/50 hover:text-text">Validation & Conditional Logic</summary>
              <div className="mt-3 pt-3 border-t border-border">
                <ValidationEditor
                  fieldType={field.field_type}
                  validation={field.validation ?? null}
                  disabled={disabled}
                  onChange={(validation) => update(index, { validation })}
                />
                <ConditionEditor
                  otherFields={fields.filter((_, i) => i !== index)}
                  condition={field.visible_when ?? null}
                  disabled={disabled}
                  onChange={(visible_when) => update(index, { visible_when })}
                />
              </div>
            </details>
          </div>
        );
      })}
      {!disabled && (
        <button
          type="button"
          onClick={() => setFields([...fields, emptyField()])}
          className="flex items-center gap-1.5 rounded-xl border border-dashed border-border px-4 py-3 text-sm text-text/60 hover:text-primary hover:border-primary w-full justify-center"
        >
          <Icon name="plus" className="h-4 w-4" />
          Add Custom Field
        </button>
      )}
    </div>
  );
}

function ValidationEditor({
  fieldType,
  validation,
  disabled,
  onChange,
}: {
  fieldType: FormField["field_type"];
  validation: FieldValidation | null;
  disabled: boolean;
  onChange: (v: FieldValidation | null) => void;
}) {
  const v = validation ?? {};
  const set = (patch: Partial<FieldValidation>) => onChange({ ...v, ...patch });

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
      <label className="text-text/60">
        Min Length
        <input type="number" value={v.min_length ?? ""} disabled={disabled} onChange={(e) => set({ min_length: e.target.value ? Number(e.target.value) : null })} className="mt-1 w-full rounded border border-border px-2 py-1 text-xs disabled:bg-background" />
      </label>
      <label className="text-text/60">
        Max Length
        <input type="number" value={v.max_length ?? ""} disabled={disabled} onChange={(e) => set({ max_length: e.target.value ? Number(e.target.value) : null })} className="mt-1 w-full rounded border border-border px-2 py-1 text-xs disabled:bg-background" />
      </label>
      {fieldType === "number" && (
        <>
          <label className="text-text/60">
            Min Value
            <input type="number" value={v.min_value ?? ""} disabled={disabled} onChange={(e) => set({ min_value: e.target.value ? Number(e.target.value) : null })} className="mt-1 w-full rounded border border-border px-2 py-1 text-xs disabled:bg-background" />
          </label>
          <label className="text-text/60">
            Max Value
            <input type="number" value={v.max_value ?? ""} disabled={disabled} onChange={(e) => set({ max_value: e.target.value ? Number(e.target.value) : null })} className="mt-1 w-full rounded border border-border px-2 py-1 text-xs disabled:bg-background" />
          </label>
        </>
      )}
      {fieldType === "date" && (
        <>
          <label className="text-text/60">
            Min Date
            <input type="date" value={v.min_date ?? ""} disabled={disabled} onChange={(e) => set({ min_date: e.target.value || null })} className="mt-1 w-full rounded border border-border px-2 py-1 text-xs disabled:bg-background" />
          </label>
          <label className="text-text/60">
            Max Date
            <input type="date" value={v.max_date ?? ""} disabled={disabled} onChange={(e) => set({ max_date: e.target.value || null })} className="mt-1 w-full rounded border border-border px-2 py-1 text-xs disabled:bg-background" />
          </label>
        </>
      )}
      <label className="text-text/60">
        Format
        <select value={v.format ?? ""} disabled={disabled} onChange={(e) => set({ format: (e.target.value || null) as FieldValidation["format"] })} className="mt-1 w-full rounded border border-border px-2 py-1 text-xs bg-card disabled:bg-background">
          {FORMATS.map((f) => (
            <option key={f} value={f}>
              {f || "None"}
            </option>
          ))}
        </select>
      </label>
      <label className="text-text/60">
        Regex Pattern
        <input value={v.pattern ?? ""} disabled={disabled} onChange={(e) => set({ pattern: e.target.value || null })} placeholder="e.g. [A-Z]{5}[0-9]{4}[A-Z]" className="mt-1 w-full rounded border border-border px-2 py-1 text-xs disabled:bg-background" />
      </label>
      <label className="text-text/60">
        Mask (display hint)
        <input value={v.mask ?? ""} disabled={disabled} onChange={(e) => set({ mask: e.target.value || null })} className="mt-1 w-full rounded border border-border px-2 py-1 text-xs disabled:bg-background" />
      </label>
      <label className="flex items-center gap-1.5 text-text/60 self-end pb-1">
        <input type="checkbox" checked={v.auto_uppercase ?? false} disabled={disabled} onChange={(e) => set({ auto_uppercase: e.target.checked })} />
        Auto Uppercase
      </label>
      <label className="flex items-center gap-1.5 text-text/60 self-end pb-1">
        <input type="checkbox" checked={v.trim ?? false} disabled={disabled} onChange={(e) => set({ trim: e.target.checked })} />
        Trim Spaces
      </label>
    </div>
  );
}

function ConditionEditor({
  otherFields,
  condition,
  disabled,
  onChange,
}: {
  otherFields: FormField[];
  condition: FieldCondition | null;
  disabled: boolean;
  onChange: (c: FieldCondition | null) => void;
}) {
  if (otherFields.length === 0) return null;
  return (
    <div className="pt-2 border-t border-border">
      <p className="text-text/50 mb-2">Show this field when…</p>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={condition?.field_key ?? ""}
          disabled={disabled}
          onChange={(e) =>
            e.target.value ? onChange({ field_key: e.target.value, operator: condition?.operator ?? "equals", value: condition?.value ?? "" }) : onChange(null)
          }
          className="rounded border border-border px-2 py-1 text-xs bg-card disabled:bg-background"
        >
          <option value="">(always visible)</option>
          {otherFields.map((f) => (
            <option key={f.key} value={f.key}>
              {f.label || f.key}
            </option>
          ))}
        </select>
        {condition && (
          <>
            <select
              value={condition.operator}
              disabled={disabled}
              onChange={(e) => onChange({ ...condition, operator: e.target.value as FieldCondition["operator"] })}
              className="rounded border border-border px-2 py-1 text-xs bg-card disabled:bg-background"
            >
              {OPERATORS.map((op) => (
                <option key={op} value={op}>
                  {op}
                </option>
              ))}
            </select>
            <input
              value={String(condition.value ?? "")}
              disabled={disabled}
              onChange={(e) => onChange({ ...condition, value: e.target.value })}
              placeholder="value"
              className="rounded border border-border px-2 py-1 text-xs disabled:bg-background"
            />
          </>
        )}
      </div>
    </div>
  );
}

function DocumentsTab({
  documents,
  setDocuments,
  disabled,
}: {
  documents: RequiredDocument[];
  setDocuments: (docs: RequiredDocument[]) => void;
  disabled: boolean;
}) {
  const update = (index: number, patch: Partial<RequiredDocument>) => {
    setDocuments(documents.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  };
  const remove = (index: number) => setDocuments(documents.filter((_, i) => i !== index));

  return (
    <div className="space-y-3 max-w-4xl">
      {documents.map((doc, index) => {
        const isMaster = doc.source === "master";
        return (
          <div key={index} className="bg-card border border-border rounded-card shadow-card p-4">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div className="flex items-center gap-2">
                {isMaster && <MasterBadge />}
                <span className="text-sm font-medium text-text">{doc.document_type_name || "New Document"}</span>
              </div>
              {!isMaster && (
                <button type="button" disabled={disabled} onClick={() => remove(index)} className="text-xs text-danger hover:underline disabled:opacity-30">
                  Delete
                </button>
              )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
              {isMaster ? (
                <label className="text-xs text-text/60">
                  Display Name Override
                  <input
                    value={doc.name_override ?? ""}
                    disabled={disabled}
                    onChange={(e) => update(index, { name_override: e.target.value || null })}
                    placeholder={doc.document_type_name}
                    className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                  />
                </label>
              ) : (
                <label className="text-xs text-text/60">
                  Document Type ID
                  <input
                    value={doc.document_type_id}
                    disabled={disabled}
                    onChange={(e) => update(index, { document_type_id: e.target.value.trim() })}
                    className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                  />
                </label>
              )}
              <label className="text-xs text-text/60">
                Section
                <input
                  value={doc.section ?? ""}
                  disabled={disabled}
                  onChange={(e) => update(index, { section: e.target.value || null })}
                  className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                />
              </label>
              <label className="text-xs text-text/60">
                Note
                <input
                  value={doc.note ?? ""}
                  disabled={disabled}
                  onChange={(e) => update(index, { note: e.target.value || null })}
                  className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                />
              </label>
              <label className="text-xs text-text/60">
                Allowed Types (comma-separated, e.g. pdf,jpg,png)
                <input
                  value={(doc.allowed_types ?? []).join(", ")}
                  disabled={disabled}
                  onChange={(e) => update(index, { allowed_types: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) || null })}
                  className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                />
              </label>
              <label className="text-xs text-text/60">
                Max Size (MB)
                <input
                  type="number"
                  value={doc.max_size_mb ?? ""}
                  disabled={disabled}
                  onChange={(e) => update(index, { max_size_mb: e.target.value ? Number(e.target.value) : null })}
                  className="mt-1 w-full rounded border border-border px-2.5 py-1.5 text-sm disabled:bg-background"
                />
              </label>
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-1.5 text-xs text-text/70">
                <input type="checkbox" checked={doc.required ?? true} disabled={disabled} onChange={(e) => update(index, { required: e.target.checked })} />
                Required
              </label>
              <label className="flex items-center gap-1.5 text-xs text-text/70">
                <input type="checkbox" checked={doc.multiple_upload ?? false} disabled={disabled} onChange={(e) => update(index, { multiple_upload: e.target.checked })} />
                Multiple Upload
              </label>
              <label className="flex items-center gap-1.5 text-xs text-text/70">
                <input type="checkbox" checked={doc.preview_enabled ?? true} disabled={disabled} onChange={(e) => update(index, { preview_enabled: e.target.checked })} />
                Preview Enabled
              </label>
              <label className="flex items-center gap-1.5 text-xs text-text/70">
                <input type="checkbox" checked={doc.hidden ?? false} disabled={disabled} onChange={(e) => update(index, { hidden: e.target.checked })} />
                Hidden
              </label>
            </div>
          </div>
        );
      })}
      {!disabled && (
        <button
          type="button"
          onClick={() => setDocuments([...documents, emptyDocument()])}
          className="flex items-center gap-1.5 rounded-xl border border-dashed border-border px-4 py-3 text-sm text-text/60 hover:text-primary hover:border-primary w-full justify-center"
        >
          <Icon name="plus" className="h-4 w-4" />
          Add Custom Document
        </button>
      )}
    </div>
  );
}

function FreezeChecklistModal({
  checkedItems,
  setCheckedItems,
  onCancel,
  onConfirm,
  isBusy,
}: {
  checkedItems: Set<string>;
  setCheckedItems: (items: Set<string>) => void;
  onCancel: () => void;
  onConfirm: () => void;
  isBusy: boolean;
}) {
  const allChecked = checkedItems.size === CHECKLIST_ITEMS.length;
  const toggle = (item: string) => {
    const next = new Set(checkedItems);
    if (next.has(item)) next.delete(item);
    else next.add(item);
    setCheckedItems(next);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-card border border-border rounded-card shadow-card max-w-md w-full p-6 max-h-[85vh] overflow-y-auto">
        <h2 className="text-base font-semibold text-text mb-1">Freeze Checklist</h2>
        <p className="text-xs text-text/50 mb-4">Confirm every item before freezing this schema version as read-only.</p>
        <div className="space-y-2 mb-5">
          {CHECKLIST_ITEMS.map((item) => (
            <label key={item} className="flex items-center gap-2 text-sm text-text/80">
              <input type="checkbox" checked={checkedItems.has(item)} onChange={() => toggle(item)} />
              {item}
            </label>
          ))}
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-xl border border-border px-3.5 py-2 text-sm font-medium text-text/70 hover:bg-background">
            Cancel
          </button>
          <button
            type="button"
            disabled={!allChecked || isBusy}
            onClick={onConfirm}
            className="rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-2 px-4 shadow-card disabled:opacity-50"
          >
            Confirm Freeze
          </button>
        </div>
      </div>
    </div>
  );
}

function HistoryTab({ entries }: { entries: SchemaAuditEntry[] | null }) {
  const eventLabels: Record<string, string> = useMemo(
    () => ({
      schema_field_updated: "Fields/Documents Updated",
      schema_frozen: "Frozen",
      schema_draft_created: "New Version Created",
      schema_published: "Published",
    }),
    [],
  );

  if (entries === null) {
    return <div className="animate-shimmer h-24 rounded-card bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%] max-w-4xl" />;
  }
  if (entries.length === 0) {
    return <p className="text-sm text-text/50">No changes recorded yet.</p>;
  }
  return (
    <div className="bg-card border border-border rounded-card shadow-card divide-y divide-border max-w-4xl">
      {entries.map((entry) => (
        <div key={entry.id} className="p-4">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-sm font-medium text-text">{eventLabels[entry.event_type] ?? entry.event_type}</span>
            <span className="text-xs text-text/40">{new Date(entry.changed_at).toLocaleString()}</span>
          </div>
          <p className="text-xs text-text/50 mb-2">By {entry.changed_by_name ?? "Owner"}</p>
          {entry.changes.length > 0 && (
            <ul className="space-y-1">
              {entry.changes.map((c, i) => (
                <li key={i} className="text-xs text-text/60">
                  <span className="font-medium">{c.key}</span> — {c.attribute}
                  {c.attribute === "field" || c.attribute === "document" ? " changed" : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
