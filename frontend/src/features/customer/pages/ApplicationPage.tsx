import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { computeProgress, validateFormData } from "@/components/forms/fieldValidation";
import { FormField } from "@/components/forms/FormField";
import { ProductSchemaForm, RepeatableGroupsForm, groupBySection } from "@/components/forms/ProductSchemaForm";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { useAuth } from "@/features/auth/useAuth";
import { DocumentChecklist } from "@/features/customer/components/DocumentChecklist";
import {
  confirmDocument,
  getApplication,
  getDocumentUploadUrl,
  getFormDefinition,
  listDocuments,
  updateApplication,
  submitApplication,
  type ApplicationDetail,
  type ApplicationDocument,
  type FormDefinition,
  type FormField as SchemaFormField,
} from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { useApplicationTabLock } from "@/features/customer/useApplicationTabLock";
import { Icon } from "@/theme/icons";

// Legacy fallback only — under the unified onboarding flow (see
// docs/decisions/DECISIONS.md #047's supersession note), every customer completes their
// profile via /portal/profile/setup right after authentication, before ever reaching
// this page, so `needsProfile` below should no longer be true for anything created
// after that change shipped. This card stays as a safety net for any application that
// was already in flight (customer_id still null) before then.
const PENDING_PROFILE_FIELDS: { key: string; label: string }[] = [
  { key: "full_name", label: "Full Name" },
  { key: "email", label: "Email" },
];

const AUTOSAVE_DEBOUNCE_MS = 1500;

type SaveState = "idle" | "unsaved" | "saving" | "saved" | "error";

type WizardStep =
  | { kind: "fields"; key: string; label: string; fields: SchemaFormField[] }
  | { kind: "documents"; key: "__documents__"; label: "Documents" }
  | { kind: "review"; key: "__review__"; label: "Review" };

function SaveStatus({ state, savedSecondsAgo }: { state: SaveState; savedSecondsAgo: number | null }) {
  if (state === "unsaved") return <span className="text-xs text-warning">Unsaved changes</span>;
  if (state === "saving") return <span className="text-xs text-text/50">Saving…</span>;
  if (state === "error") return <span className="text-xs text-danger">Couldn't save — will retry on your next change.</span>;
  if (state === "saved" && savedSecondsAgo !== null) {
    return <span className="text-xs text-success">Saved {savedSecondsAgo <= 1 ? "just now" : `${savedSecondsAgo} seconds ago`}</span>;
  }
  return null;
}

export function ApplicationPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { registerPreLogoutFlush } = useAuth();
  const [application, setApplication] = useState<ApplicationDetail | null>(null);
  const [formDef, setFormDef] = useState<FormDefinition | null>(null);
  const [documents, setDocuments] = useState<ApplicationDocument[]>([]);
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [pendingProfile, setPendingProfile] = useState<Record<string, unknown>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadingFor, setUploadingFor] = useState<string | null>(null);
  const { status: tabLockStatus, takeOver: takeOverTabLock } = useApplicationTabLock(id);
  // Restores "Same Step" after an idle auto-logout or a plain browser refresh — the
  // draft itself is already safe via autosave (below); this just keeps the wizard from
  // dumping the customer back at step 1 on return.
  const [stepIndex, setStepIndex] = useState(() => {
    if (!id) return 0;
    const saved = sessionStorage.getItem(`afs_app_step_${id}`);
    return saved ? Number(saved) : 0;
  });

  // Phase 3.1 — Auto Save / Resume Later: every change is persisted a short beat after
  // the user stops typing; reopening this page (`load()` below) already restores
  // whatever was last auto-saved. The Customer Portal redesign adds an explicit "Save
  // Draft" button and an "Unsaved changes" indicator alongside it — same mechanism,
  // more visible confidence signal.
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipNextAutosave = useRef(true);

  const load = () => {
    if (!id) return;
    getApplication(id)
      .then(async (app) => {
        setApplication(app);
        setFormData(app.form_data ?? {});
        skipNextAutosave.current = true;
        const def = await getFormDefinition(app.product_category, app.product_id);
        setFormDef(def);
        const docs = await listDocuments(id);
        setDocuments(docs);
      })
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [id]);

  useEffect(() => {
    if (!id) return;
    sessionStorage.setItem(`afs_app_step_${id}`, String(stepIndex));
  }, [id, stepIndex]);

  useEffect(() => {
    const interval = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  const isSubmitted = application?.status === "submitted";
  const needsProfile = application?.customer_id === null;
  const hasUnsavedChanges = saveState === "unsaved" || saveState === "saving";

  // Debounced autosave — fires on any formData/pendingProfile change once the initial
  // load has settled, skipping the very first render after `load()` sets state so
  // opening the page never immediately re-saves what the server just returned.
  useEffect(() => {
    if (!id || isSubmitted) return;
    if (skipNextAutosave.current) {
      skipNextAutosave.current = false;
      return;
    }
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    autosaveTimer.current = setTimeout(async () => {
      setSaveState("saving");
      try {
        await updateApplication(id, { form_data: formData, pending_profile: needsProfile ? pendingProfile : undefined });
        setSaveState("saved");
        setSavedAt(new Date());
      } catch {
        setSaveState("error");
      }
    }, AUTOSAVE_DEBOUNCE_MS);
    return () => {
      if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formData, pendingProfile]);

  // Tab close/refresh with unsaved changes — a real "are you sure" the browser itself
  // surfaces, not a custom modal (browsers ignore custom text here, so none is passed).
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (!hasUnsavedChanges) return;
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [hasUnsavedChanges]);

  // Every logout path (manual click, idle auto-logout — see AuthProvider.logout /
  // SessionGuard.tsx) flushes any pending autosave first, so a click mid-keystroke can
  // never drop the last few seconds of edits.
  useEffect(() => {
    if (!id) return;
    registerPreLogoutFlush(async () => {
      if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
      if (!hasUnsavedChanges) return;
      await updateApplication(id, { form_data: formData, pending_profile: needsProfile ? pendingProfile : undefined });
    });
    return () => registerPreLogoutFlush(null);
  }, [id, registerPreLogoutFlush, hasUnsavedChanges, formData, pendingProfile, needsProfile]);

  const steps = useMemo<WizardStep[]>(() => {
    if (!formDef) return [];
    // Sectioned by the schema's own field list — `ProductSchemaForm`/`validateFormData`
    // both already re-check each field's own `visible_when` against live values, so a
    // step can safely carry a conditionally-hidden field without rendering or validating it.
    const sections = groupBySection(formDef.fields);
    const fieldSteps: WizardStep[] = sections.map(([sectionName, fields], i) => ({
      kind: "fields",
      key: sectionName ?? `section-${i}`,
      label: sectionName ?? "Application Details",
      fields,
    }));
    return [...fieldSteps, { kind: "documents", key: "__documents__", label: "Documents" }, { kind: "review", key: "__review__", label: "Review" }];
  }, [formDef]);

  if (!id) return null;
  if (error && !application) return <ErrorBanner message={error} />;
  if (!application || !formDef) {
    return (
      <div className="max-w-app mx-auto space-y-4">
        <div className="animate-shimmer h-10 rounded-lg bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%]" />
        <div className="animate-shimmer h-64 rounded-lg bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%]" />
      </div>
    );
  }

  const currentStep = steps[stepIndex] ?? steps[0];

  const onFieldChange = (key: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setSaveState("unsaved");
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const { [key]: _removed, ...rest } = prev;
      return rest;
    });
  };
  const onGroupChange = (groupKey: string, blocks: Record<string, unknown>[]) => {
    setFormData((prev) => ({ ...prev, [groupKey]: blocks }));
    setSaveState("unsaved");
  };
  const onProfileChange = (key: string, value: unknown) => {
    setPendingProfile((prev) => ({ ...prev, [key]: value }));
    setSaveState("unsaved");
  };

  const onUploadDocument = async (documentTypeId: string, file: File) => {
    setError(null);
    setUploadingFor(documentTypeId);
    try {
      const { upload_url, s3_key } = await getDocumentUploadUrl(id, documentTypeId, file.name, file.type);
      await fetch(upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
      await confirmDocument(id, documentTypeId, file.name, s3_key, file.type);
      const docs = await listDocuments(id);
      setDocuments(docs);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUploadingFor(null);
    }
  };

  const onSaveDraft = async () => {
    if (!id) return;
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    setSaveState("saving");
    try {
      await updateApplication(id, { form_data: formData, pending_profile: needsProfile ? pendingProfile : undefined });
      setSaveState("saved");
      setSavedAt(new Date());
    } catch (err) {
      setSaveState("error");
      setError(getErrorMessage(err));
    }
  };

  const onBack = () => {
    if (hasUnsavedChanges && !window.confirm("You have unsaved changes. Leave without saving?")) return;
    navigate("/portal/applications");
  };

  const onNext = () => {
    setError(null);
    if (currentStep.kind === "fields") {
      const errors = validateFormData(currentStep.fields, formData);
      if (Object.keys(errors).length > 0) {
        setFieldErrors((prev) => ({ ...prev, ...errors }));
        setError("Please fix the highlighted fields before continuing.");
        return;
      }
    }
    setStepIndex((i) => Math.min(i + 1, steps.length - 1));
  };
  const onPrevious = () => {
    setError(null);
    setStepIndex((i) => Math.max(i - 1, 0));
  };

  const onSubmit = async () => {
    setError(null);
    const errors = validateFormData(formDef.fields, formData);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setError("Please fix the highlighted fields before submitting.");
      const firstBadStep = steps.findIndex((s) => s.kind === "fields" && s.fields.some((f) => errors[f.key]));
      if (firstBadStep >= 0) setStepIndex(firstBadStep);
      return;
    }
    setIsSubmitting(true);
    try {
      const profile = needsProfile
        ? { full_name: String(pendingProfile.full_name ?? ""), email: (pendingProfile.email as string) || undefined }
        : undefined;
      await submitApplication(id, profile);
      navigate("/portal/applications");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const progress = computeProgress(formDef.fields, formData);
  const savedSecondsAgo = savedAt ? Math.floor((nowTick - savedAt.getTime()) / 1000) : null;
  const statusLabel = application.status === "submitted" ? "Submitted" : "Draft";
  const documentsComplete = formDef.required_documents.every((rd) => documents.some((d) => d.document_type_id === rd.document_type_id));

  const isStepComplete = (step: WizardStep): boolean => {
    if (step.kind === "fields") return computeProgress(step.fields, formData) === 100;
    if (step.kind === "documents") return documentsComplete;
    return false;
  };

  return (
    <div className="max-w-app mx-auto">
      {tabLockStatus === "conflict" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="w-full max-w-sm rounded-card bg-card border border-border shadow-card p-6 text-center">
            <h2 className="text-lg font-semibold text-text mb-2">Already Open</h2>
            <p className="text-sm text-text/60 mb-6">Application already opened in another tab. Continue here?</p>
            <div className="flex flex-col gap-2">
              <button type="button" onClick={takeOverTabLock} className="w-full rounded-lg bg-primary text-white text-sm font-medium py-2.5">
                Continue
              </button>
              <button
                type="button"
                onClick={() => navigate("/portal/applications")}
                className="w-full rounded-lg border border-border text-sm font-medium py-2.5 text-text/70 hover:bg-background"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
      <button type="button" onClick={onBack} className="mb-3 text-sm text-primary hover:underline">
        ← Back to My Applications
      </button>

      <div className="flex items-center justify-between mb-1">
        <h1 className="text-xl font-semibold text-text">{application.application_code}</h1>
        <span className="text-xs font-medium rounded-full px-2 py-1 bg-primary/10 text-primary">{statusLabel}</span>
      </div>
      <p className="text-sm text-text/60 mb-4">{application.product_name}</p>

      {!isSubmitted && (
        <>
          {/* Sticky step progress bar */}
          <div className="sticky top-0 z-10 -mx-6 mb-6 bg-background/95 backdrop-blur px-6 py-3 border-b border-border">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-text/60">Application Progress</span>
              <span className="text-xs font-medium text-text/60">{progress}%</span>
            </div>
            <div className="h-2 rounded-full bg-border overflow-hidden mb-3">
              <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
            </div>
            <div className="flex flex-wrap items-center gap-x-1 gap-y-2 text-xs">
              {steps.map((step, i) => {
                const complete = isStepComplete(step);
                const isCurrent = i === stepIndex;
                return (
                  <button
                    key={step.key}
                    type="button"
                    onClick={() => setStepIndex(i)}
                    className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 font-medium transition-colors ${
                      isCurrent ? "bg-primary text-white" : complete ? "text-success" : "text-text/50 hover:text-text"
                    }`}
                  >
                    {complete && !isCurrent ? <Icon name="check-circle" className="h-3.5 w-3.5" /> : <span>{i + 1}.</span>}
                    {step.label}
                  </button>
                );
              })}
            </div>
            <div className="mt-1.5">
              <SaveStatus state={saveState} savedSecondsAgo={savedSecondsAgo} />
            </div>
          </div>
        </>
      )}

      <ErrorBanner message={error} />

      {needsProfile && !isSubmitted && stepIndex === 0 && (
        <div className="bg-card border border-border rounded-card shadow-card p-6 mb-6">
          <h2 className="text-sm font-semibold text-text/70 mb-3">Your Details</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6">
            {PENDING_PROFILE_FIELDS.map((f) => (
              <FormField
                key={f.key}
                label={f.label}
                value={(pendingProfile[f.key] as string) ?? ""}
                onChange={(e) => onProfileChange(f.key, e.target.value)}
              />
            ))}
          </div>
        </div>
      )}

      {isSubmitted ? (
        <>
          <div className="bg-card border border-border rounded-card shadow-card p-6 mb-6">
            <h2 className="text-sm font-semibold text-text/70 mb-3">Application Details</h2>
            <ProductSchemaForm fields={formDef.fields} values={formData} onChange={onFieldChange} disabled errors={fieldErrors} />
            <RepeatableGroupsForm groups={formDef.repeatable_groups} values={formData} onChange={onGroupChange} disabled />
          </div>
          <div className="bg-card border border-border rounded-card shadow-card p-6 mb-6">
            <h2 className="text-sm font-semibold text-text/70 mb-4">Documents</h2>
            <DocumentChecklist
              requiredDocuments={formDef.required_documents}
              uploadedDocuments={documents}
              onUpload={onUploadDocument}
              uploadingFor={uploadingFor}
              disabled
            />
          </div>
        </>
      ) : (
        <>
          {currentStep.kind === "fields" && (
            <div className="bg-card border border-border rounded-card shadow-card p-6 mb-6">
              <h2 className="text-sm font-semibold text-text/70 mb-3">{currentStep.label}</h2>
              <ProductSchemaForm fields={currentStep.fields} values={formData} onChange={onFieldChange} errors={fieldErrors} />
            </div>
          )}

          {currentStep.kind === "documents" && (
            <div className="bg-card border border-border rounded-card shadow-card p-6 mb-6">
              <h2 className="text-sm font-semibold text-text/70 mb-4">Required Documents</h2>
              <DocumentChecklist
                requiredDocuments={formDef.required_documents}
                uploadedDocuments={documents}
                onUpload={onUploadDocument}
                uploadingFor={uploadingFor}
              />
            </div>
          )}

          {currentStep.kind === "review" && (
            <div className="space-y-4 mb-6">
              <div className="bg-card border border-border rounded-card shadow-card p-6">
                <h2 className="text-sm font-semibold text-text/70 mb-4">Review Your Application</h2>
                {groupBySection(formDef.fields).map(([sectionName, fields]) => (
                  <div key={sectionName ?? "_default"} className="mb-4 last:mb-0">
                    {sectionName && <h3 className="text-xs font-semibold uppercase tracking-wide text-text/40 mb-2">{sectionName}</h3>}
                    <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2">
                      {fields.map((f) => (
                        <div key={f.key}>
                          <dt className="text-xs text-text/50">{f.label}</dt>
                          <dd className="text-sm text-text">{String(formData[f.key] ?? "—")}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
                <RepeatableGroupsForm groups={formDef.repeatable_groups} values={formData} onChange={onGroupChange} disabled />
              </div>
              <div className="bg-card border border-border rounded-card shadow-card p-6">
                <h2 className="text-sm font-semibold text-text/70 mb-4">Documents</h2>
                <DocumentChecklist
                  requiredDocuments={formDef.required_documents}
                  uploadedDocuments={documents}
                  onUpload={onUploadDocument}
                  uploadingFor={uploadingFor}
                />
              </div>
            </div>
          )}

          {/* Sticky footer */}
          <div className="sticky bottom-0 -mx-6 mt-6 bg-card border-t border-border px-6 py-4 flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={onPrevious}
              disabled={stepIndex === 0}
              className="rounded-lg border border-border text-sm font-medium py-2.5 px-5 text-text/70 disabled:opacity-40"
            >
              Previous
            </button>
            <div className="flex items-center gap-3">
              <button type="button" onClick={onSaveDraft} className="rounded-lg border border-border text-sm font-medium py-2.5 px-5 text-text/70 hover:bg-background">
                Save Draft
              </button>
              {currentStep.kind === "review" ? (
                <SubmitButton isSubmitting={isSubmitting} onClick={onSubmit}>
                  Submit Application
                </SubmitButton>
              ) : (
                <button type="button" onClick={onNext} className="rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-2.5 px-5 shadow-card">
                  Next
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
