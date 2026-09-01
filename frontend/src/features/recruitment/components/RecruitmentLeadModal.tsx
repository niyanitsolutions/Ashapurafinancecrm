import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import {
  GENDERS,
  PROFESSIONS,
  createRecruitmentLead,
  getRecruitmentLookup,
  moveRecruitmentBackToFresh,
  moveRecruitmentToBop,
  moveRecruitmentToDocCollection,
  rejectRecruitmentLead,
  updateRecruitmentLead,
  type RecruitmentLeadDetail,
} from "@/features/recruitment/api";
import { GENDER_LABELS, PROFESSION_LABELS } from "@/features/recruitment/labels";
import { getErrorMessage } from "@/shared/api/errors";

type Mode = "create" | "fresh" | "bop";

interface FormState {
  full_name: string;
  mobile: string;
  email: string;
  gender: string;
  age: string;
  source_id: string;
  profession: string;
  other_profession: string;
  remarks: string;
}

function initialState(lead: RecruitmentLeadDetail | null): FormState {
  return {
    full_name: lead?.full_name ?? "",
    mobile: lead?.mobile ?? "",
    email: lead?.email ?? "",
    gender: lead?.gender ?? "",
    age: lead ? String(lead.age) : "",
    source_id: lead?.source_id ?? "",
    profession: lead?.profession ?? "",
    other_profession: lead?.other_profession ?? "",
    remarks: lead?.remarks ?? "",
  };
}

export function RecruitmentLeadModal({
  mode,
  lead,
  onClose,
  onSaved,
}: {
  mode: Mode;
  lead: RecruitmentLeadDetail | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<FormState>(() => initialState(lead));
  const [sources, setSources] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  useEffect(() => {
    getRecruitmentLookup()
      .then((data) => setSources(data.sources))
      .catch(() => undefined);
  }, []);

  const set = <K extends keyof FormState>(key: K, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const title = mode === "create" ? "Add Recruitment Lead" : mode === "bop" ? "Update — BOP" : "Update Recruitment Lead";

  const buildPayload = () => ({
    full_name: form.full_name.trim(),
    mobile: form.mobile.trim(),
    email: form.email.trim() || null,
    gender: form.gender,
    age: Number(form.age),
    source_id: form.source_id,
    profession: form.profession,
    other_profession: form.profession === "other" ? form.other_profession.trim() : null,
    remarks: form.remarks.trim() || null,
  });

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const persistDetails = async () => {
    if (mode === "create") {
      await createRecruitmentLead(buildPayload());
    } else if (lead) {
      await updateRecruitmentLead(lead.id, buildPayload());
    }
  };

  const onSave = () => run(persistDetails);

  const onSaveAndMoveToBop = () =>
    run(async () => {
      if (mode === "create") {
        const created = await createRecruitmentLead(buildPayload());
        await moveRecruitmentToBop(created.id);
      } else if (lead) {
        await updateRecruitmentLead(lead.id, buildPayload());
        await moveRecruitmentToBop(lead.id);
      }
    });

  const onMoveToDocCollection = () =>
    run(async () => {
      if (!lead) return;
      await updateRecruitmentLead(lead.id, buildPayload());
      await moveRecruitmentToDocCollection(lead.id);
    });

  const onBackToFresh = () => run(async () => lead && moveRecruitmentBackToFresh(lead.id));

  const onConfirmReject = () =>
    run(async () => {
      if (!lead) return;
      await rejectRecruitmentLead(lead.id, rejectReason.trim());
    });

  const footer = rejecting ? (
    <>
      <Button variant="secondary" size="sm" onClick={() => setRejecting(false)} disabled={busy}>
        Back
      </Button>
      <Button variant="danger" size="sm" onClick={onConfirmReject} loading={busy} disabled={!rejectReason.trim()}>
        Confirm Reject
      </Button>
    </>
  ) : mode === "bop" ? (
    <>
      <Button variant="secondary" size="sm" onClick={onBackToFresh} disabled={busy}>
        Back to Fresh
      </Button>
      <Button variant="danger" size="sm" onClick={() => setRejecting(true)} disabled={busy}>
        Reject
      </Button>
      <Button size="sm" onClick={onMoveToDocCollection} loading={busy}>
        Move to Document Collection
      </Button>
    </>
  ) : (
    <>
      <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
        Close
      </Button>
      {mode === "fresh" && (
        <Button variant="danger" size="sm" onClick={() => setRejecting(true)} disabled={busy}>
          Reject
        </Button>
      )}
      <Button variant="secondary" size="sm" onClick={onSave} loading={busy}>
        Save
      </Button>
      <Button size="sm" onClick={onSaveAndMoveToBop} loading={busy}>
        Save &amp; Move to BOP
      </Button>
    </>
  );

  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      description={lead ? `${lead.recruitment_code} · ${STAGE_HINT[mode]}` : "New candidate to become an insurance advisor"}
      size="lg"
      footer={footer}
    >
      {error && <ErrorBanner message={error} />}

      {rejecting ? (
        <TextareaField
          label="Rejection reason"
          id="rec-reject-reason"
          rows={4}
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder="Why is this recruitment lead being rejected?"
        />
      ) : (
        <>
          <p className="mb-3 text-2xs font-semibold uppercase tracking-wide text-textSecondary">Personal information</p>
          <div className="grid gap-x-4 sm:grid-cols-2">
            <FormField label="Name" name="full_name" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} />
            <FormField label="Mobile Number" name="mobile" value={form.mobile} onChange={(e) => set("mobile", e.target.value)} />
            <FormField label="Email" name="email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
            <FormField label="Age" name="age" type="number" value={form.age} onChange={(e) => set("age", e.target.value)} />
            <SelectField
              label="Gender"
              name="gender"
              value={form.gender}
              onChange={(e) => set("gender", e.target.value)}
              placeholder="Select gender"
              options={GENDERS.map((g) => ({ value: g, label: GENDER_LABELS[g] }))}
            />
            <SelectField
              label="Source"
              name="source_id"
              value={form.source_id}
              onChange={(e) => set("source_id", e.target.value)}
              placeholder="Select source"
              options={sources.map((s) => ({ value: s.id, label: s.name }))}
            />
            <SelectField
              label="Profession"
              name="profession"
              value={form.profession}
              onChange={(e) => set("profession", e.target.value)}
              placeholder="Select profession"
              options={PROFESSIONS.map((p) => ({ value: p, label: PROFESSION_LABELS[p] }))}
            />
            {form.profession === "other" && (
              <FormField
                label="Other Profession"
                name="other_profession"
                value={form.other_profession}
                onChange={(e) => set("other_profession", e.target.value)}
              />
            )}
          </div>
          <TextareaField
            label="Remarks"
            name="remarks"
            rows={3}
            value={form.remarks}
            onChange={(e) => set("remarks", e.target.value)}
          />
          <div className="mt-1 rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm">
            <span className="text-textSecondary">Stage: </span>
            <span className="font-semibold text-text">
              {mode === "create" ? "Fresh Leads" : mode === "bop" ? "BOP" : "Fresh Leads"}
            </span>
          </div>
        </>
      )}
    </Modal>
  );
}

const STAGE_HINT: Record<Mode, string> = {
  create: "New — Fresh Leads",
  fresh: "Fresh Leads",
  bop: "BOP → Document Collection",
};
