import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import {
  ADVISOR_PRODUCT_CATEGORIES,
  addAdvisorBusiness,
  type AddBusinessPayload,
} from "@/features/recruitment/api";
import { ADVISOR_PRODUCT_CATEGORY_LABELS } from "@/features/recruitment/labels";
import { getErrorMessage } from "@/shared/api/errors";

const EMPTY = {
  customer_name: "",
  customer_mobile: "",
  policy_number: "",
  product_category: "",
  custom_category: "",
  product_name: "",
  premium: "",
  ppt: "",
  pt: "",
  policy_issue_date: "",
  comment: "",
};

export function AddBusinessModal({
  advisorId,
  onClose,
  onSaved,
}: {
  advisorId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (key: keyof typeof EMPTY, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const canSubmit =
    form.product_category !== "" &&
    form.product_name.trim() !== "" &&
    form.premium !== "" &&
    form.ppt !== "" &&
    form.pt !== "" &&
    form.policy_issue_date !== "" &&
    (form.product_category !== "custom" || form.custom_category.trim() !== "");

  const onSave = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload: AddBusinessPayload = {
        product_category: form.product_category as AddBusinessPayload["product_category"],
        product_name: form.product_name.trim(),
        premium: Number(form.premium),
        ppt: Number(form.ppt),
        pt: Number(form.pt),
        policy_issue_date: form.policy_issue_date,
      };
      if (form.product_category === "custom") payload.custom_category = form.custom_category.trim();
      if (form.customer_name.trim()) payload.customer_name = form.customer_name.trim();
      if (form.customer_mobile.trim()) payload.customer_mobile = form.customer_mobile.trim();
      if (form.policy_number.trim()) payload.policy_number = form.policy_number.trim();
      if (form.comment.trim()) payload.comment = form.comment.trim();

      await addAdvisorBusiness(advisorId, payload);
      setForm({ ...EMPTY }); // reset the form after a successful save
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const footer = (
    <>
      <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
        Close
      </Button>
      <Button size="sm" onClick={onSave} loading={busy} disabled={!canSubmit}>
        Save
      </Button>
    </>
  );

  return (
    <Modal open onClose={onClose} title="Add Business" description="Business Details" size="lg" footer={footer}>
      {error && <ErrorBanner message={error} />}

      <div className="grid gap-x-4 sm:grid-cols-2">
        <FormField
          id="biz-customer-name"
          name="customer_name"
          label="Customer Name"
          value={form.customer_name}
          onChange={(e) => set("customer_name", e.target.value)}
        />
        <FormField
          id="biz-customer-mobile"
          name="customer_mobile"
          label="Customer Mobile"
          value={form.customer_mobile}
          onChange={(e) => set("customer_mobile", e.target.value)}
        />
        <FormField
          id="biz-policy-number"
          name="policy_number"
          label="Policy Number"
          value={form.policy_number}
          onChange={(e) => set("policy_number", e.target.value)}
        />
        <SelectField
          id="biz-category"
          label="Product Category"
          value={form.product_category}
          onChange={(e) => set("product_category", e.target.value)}
          placeholder="Select category"
          options={ADVISOR_PRODUCT_CATEGORIES.map((c) => ({ value: c, label: ADVISOR_PRODUCT_CATEGORY_LABELS[c] }))}
        />
        {form.product_category === "custom" && (
          <FormField
            id="biz-custom-category"
            label="Custom Category"
            value={form.custom_category}
            onChange={(e) => set("custom_category", e.target.value)}
          />
        )}
        <FormField
          id="biz-product-name"
          label="Product Name"
          value={form.product_name}
          onChange={(e) => set("product_name", e.target.value)}
        />
        <FormField
          id="biz-premium"
          label="Premium"
          type="number"
          min={0}
          value={form.premium}
          onChange={(e) => set("premium", e.target.value)}
        />
        <FormField
          id="biz-ppt"
          label="PPT (years)"
          type="number"
          min={1}
          step={1}
          value={form.ppt}
          onChange={(e) => set("ppt", e.target.value)}
        />
        <FormField
          id="biz-pt"
          label="PT (years)"
          type="number"
          min={1}
          step={1}
          value={form.pt}
          onChange={(e) => set("pt", e.target.value)}
        />
        <FormField
          id="biz-issue-date"
          label="Policy Issue Date"
          type="date"
          value={form.policy_issue_date}
          onChange={(e) => set("policy_issue_date", e.target.value)}
        />
      </div>
      <TextareaField
        id="biz-comment"
        label="Comment"
        rows={2}
        value={form.comment}
        onChange={(e) => set("comment", e.target.value)}
      />
    </Modal>
  );
}
