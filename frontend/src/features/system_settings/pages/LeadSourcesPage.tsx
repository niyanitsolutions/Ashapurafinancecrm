import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { listCaptureSources, updateCaptureSource, type CaptureSource } from "@/features/lead_capture/api";
import {
  insuranceCategoriesApi,
  insuranceProductsApi,
  leadSourcesApi,
  loanProductsApi,
  type InsuranceProduct,
  type NamedMasterData,
} from "@/features/system_settings/api";
import { getErrorMessage } from "@/features/system_settings/errors";
import { NamedMasterDataPage } from "@/features/system_settings/pages/NamedMasterDataPage";

type ProductCategory = "loan" | "insurance";
type ProductOption = { id: string; name: string };

export function LeadSourcesPage() {
  return (
    <NamedMasterDataPage
      title="Lead Sources"
      createPlaceholder="e.g. Website"
      api={leadSourcesApi}
      renderEditExtension={(item) => <MetaProductMapping leadSource={item} />}
    />
  );
}

function MetaProductMapping({ leadSource }: { leadSource: NamedMasterData }) {
  const [metaSource, setMetaSource] = useState<CaptureSource | null | undefined>(undefined);
  const [loanProducts, setLoanProducts] = useState<ProductOption[]>([]);
  const [insuranceProducts, setInsuranceProducts] = useState<ProductOption[]>([]);
  const [category, setCategory] = useState<ProductCategory | "">("");
  const [productId, setProductId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([listCaptureSources(), loanProductsApi.list(), insuranceProductsApi.list(), insuranceCategoriesApi.list()])
      .then(([sources, loans, insurance, insuranceCategories]) => {
        if (!active) return;
        const source = sources.find((candidate) => candidate.key === "meta_lead_ads" && candidate.lead_source_id === leadSource.id) ?? null;
        setMetaSource(source);
        if (!source) return;

        const activeInsuranceCategoryIds = new Set(
          insuranceCategories.filter((item) => item.status === "active").map((item) => item.id),
        );
        setLoanProducts(loans.filter((item) => item.status === "active").map(toProductOption));
        setInsuranceProducts(
          insurance
            .filter((item) => item.status === "active" && item.category_id && activeInsuranceCategoryIds.has(item.category_id))
            .map(toProductOption),
        );
        setCategory(source.default_product_category === "loan" || source.default_product_category === "insurance" ? source.default_product_category : "");
        setProductId(source.default_product_id ?? "");
      })
      .catch((err) => active && setError(getErrorMessage(err)));
    return () => {
      active = false;
    };
  }, [leadSource.id]);

  const products = useMemo(
    () => (category === "loan" ? loanProducts : category === "insurance" ? insuranceProducts : []),
    [category, insuranceProducts, loanProducts],
  );

  if (metaSource === null) return null;
  if (metaSource === undefined && !error) return <p className="text-xs text-text/50">Loading Meta Lead Ads mapping…</p>;

  const save = async () => {
    if (!metaSource || !category || !productId) {
      setError("Select both a Product Category and Product. Meta imports stay blocked until this mapping is complete.");
      return;
    }
    setError(null);
    setMessage(null);
    setSaving(true);
    try {
      const updated = await updateCaptureSource(metaSource.key, {
        default_product_category: category,
        default_product_id: productId,
      });
      setMetaSource(updated);
      setMessage("Meta Lead Ads product mapping saved.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <h3 className="text-sm font-semibold text-text">Meta Lead Ads product mapping</h3>
      <p className="mt-1 text-xs text-text/60">
        Every Meta lead imported through this source will use this product. Only active products are available.
      </p>
      {!category || !productId ? (
        <p role="alert" className="mt-3 rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
          Meta imports are blocked until both a Product Category and Product are saved.
        </p>
      ) : null}
      <ErrorBanner message={error} />
      {message && <p className="mt-3 text-sm text-success">{message}</p>}
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="text-xs text-text/60">
          Product Category
          <select
            aria-label="Meta Product Category"
            value={category}
            onChange={(event) => {
              setCategory(event.target.value as ProductCategory | "");
              setProductId("");
              setMessage(null);
            }}
            className="mt-1 block min-w-48 rounded-xl border border-border bg-card px-3 py-2 text-sm text-text"
          >
            <option value="">Select category</option>
            <option value="loan">Loan</option>
            <option value="insurance">Insurance</option>
          </select>
        </label>
        <label className="text-xs text-text/60">
          Product
          <select
            aria-label="Meta Product"
            value={productId}
            disabled={!category}
            onChange={(event) => setProductId(event.target.value)}
            className="mt-1 block min-w-64 rounded-xl border border-border bg-card px-3 py-2 text-sm text-text disabled:opacity-50"
          >
            <option value="">Select product</option>
            {products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
          </select>
        </label>
        <Button size="sm" onClick={save} disabled={saving || !category || !productId}>
          {saving ? "Saving…" : "Save Meta Mapping"}
        </Button>
      </div>
    </div>
  );
}

function toProductOption(product: NamedMasterData | InsuranceProduct): ProductOption {
  return { id: product.id, name: product.name };
}
