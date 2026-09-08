import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SelectField } from "@/components/forms/SelectField";
import { Modal } from "@/components/overlays/Modal";
import { createProductSchema, listCreatableProducts, type CreatableProduct } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";

// Insurance Policy Leads redesign (spec §7) — create a Product Schema for a product that
// has none yet, so an Owner can add an insurance product + configure its documents with
// no code change. Starts a DRAFT; the editor opens next.
export function NewSchemaModal({ onClose, onCreated }: { onClose: () => void; onCreated: (schemaId: string) => void }) {
  const [category, setCategory] = useState<"insurance" | "loan">("insurance");
  const [products, setProducts] = useState<CreatableProduct[]>([]);
  const [productId, setProductId] = useState("");
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setLoadingProducts(true);
    setProductId("");
    listCreatableProducts(category)
      .then((rows) => setProducts(rows))
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoadingProducts(false));
  }, [category]);

  const onCreate = async () => {
    setBusy(true);
    setError(null);
    try {
      const schema = await createProductSchema({
        product_category: category,
        product_id: productId,
        fields: [],
        required_documents: [],
      });
      onCreated(schema.id);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const productOptions = products.map((p) => ({
    value: p.id,
    label: category === "insurance" && p.category_name ? `${p.name} — ${p.category_name}` : p.name,
  }));

  return (
    <Modal
      open
      onClose={onClose}
      title="New Product Schema"
      description="Pick a product with no schema yet, then configure its fields and documents."
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button size="sm" onClick={onCreate} loading={busy} disabled={!productId}>
            Create &amp; Configure
          </Button>
        </>
      }
    >
      {error && <ErrorBanner message={error} />}
      <SelectField
        id="new-schema-category"
        label="Product Category"
        value={category}
        onChange={(e) => setCategory(e.target.value as "insurance" | "loan")}
        options={[
          { value: "insurance", label: "Insurance" },
          { value: "loan", label: "Loan" },
        ]}
      />
      {loadingProducts ? (
        <p className="text-sm text-textSecondary">Loading products…</p>
      ) : products.length === 0 ? (
        <p className="text-sm text-textSecondary">
          Every {category} product already has a schema. Add a new product in Settings first
          {category === "insurance" ? " (and assign it a category)" : ""}.
        </p>
      ) : (
        <SelectField
          id="new-schema-product"
          label="Product"
          value={productId}
          onChange={(e) => setProductId(e.target.value)}
          placeholder="Select a product"
          options={productOptions}
        />
      )}
    </Modal>
  );
}
