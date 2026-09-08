import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import { listPortalProducts } from "@/features/customer/api";
import type { InsuranceCaseDetail } from "@/features/insurance_management/api";
import type { NamedMasterData } from "@/features/system_settings/api";

export interface PolicyLoginUpdatePayload {
  product_id?: string;
  premium_amount?: number;
  ppt?: number;
  pt?: number;
  remarks?: string;
  policy_number?: string;
}

// Policy Login "Update" — records Premium / PPT / PT / Remarks / Policy Number, and can
// switch the product in the same call (the backend re-resolves the Product Schema and
// keeps every uploaded document). PPT/PT are integer years; Premium is a positive amount.
export function PolicyLoginUpdateModal({
  detail,
  submitting = false,
  error,
  onCancel,
  onConfirm,
}: {
  detail: InsuranceCaseDetail;
  submitting?: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: (payload: PolicyLoginUpdatePayload) => void;
}) {
  const d = detail.insurance_details;
  const [productId, setProductId] = useState(detail.product_id);
  const [products, setProducts] = useState<NamedMasterData[]>([]);
  const [premium, setPremium] = useState(d.premium_amount != null ? String(d.premium_amount) : "");
  const [ppt, setPpt] = useState(d.ppt != null ? String(d.ppt) : "");
  const [pt, setPt] = useState(d.pt != null ? String(d.pt) : "");
  const [policyNumber, setPolicyNumber] = useState(d.policy_number ?? "");
  const [remarks, setRemarks] = useState(d.policy_login_remarks ?? "");

  useEffect(() => {
    listPortalProducts("insurance").then(setProducts).catch(() => setProducts([]));
  }, []);

  const productOptions = (
    products.some((p) => p.id === detail.product_id) ? products : [{ id: detail.product_id, name: detail.product_name }, ...products]
  ).map((p) => ({ value: p.id, label: p.name }));

  const submit = () => {
    onConfirm({
      product_id: productId !== detail.product_id ? productId : undefined,
      premium_amount: premium ? Number(premium) : undefined,
      ppt: ppt ? Number(ppt) : undefined,
      pt: pt ? Number(pt) : undefined,
      policy_number: policyNumber.trim() || undefined,
      remarks: remarks.trim() || undefined,
    });
  };

  return (
    <Modal open onClose={onCancel} title="Update Policy Login" description={`Case ${detail.case_code}`}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="space-y-3"
      >
        {error && <p className="text-sm text-danger">{error}</p>}

        <SelectField
          label="Product"
          name="policy_login_product"
          value={productId}
          onChange={(e) => setProductId(e.target.value)}
          options={productOptions}
        />
        {productId !== detail.product_id && (
          <p className="-mt-2 text-xs text-warning">
            Changing the product re-resolves the document checklist. Uploaded documents are kept.
          </p>
        )}

        <FormField label="Premium Amount" name="premium_amount" type="number" min="0" step="0.01" value={premium} onChange={(e) => setPremium(e.target.value)} />
        <div className="grid grid-cols-2 gap-3">
          <FormField label="PPT (years)" name="ppt" type="number" min="1" value={ppt} onChange={(e) => setPpt(e.target.value)} />
          <FormField label="PT (years)" name="pt" type="number" min="1" value={pt} onChange={(e) => setPt(e.target.value)} />
        </div>
        <FormField label="Policy Number" name="policy_number" value={policyNumber} onChange={(e) => setPolicyNumber(e.target.value)} />
        <TextareaField label="Remarks" name="policy_login_remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />

        <div className="flex gap-2 pt-1">
          <Button type="submit" className="flex-1" loading={submitting} disabled={submitting}>
            Save
          </Button>
          <Button type="button" variant="secondary" className="flex-1" disabled={submitting} onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
}
