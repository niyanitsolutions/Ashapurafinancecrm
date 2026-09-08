import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import {
  listOwnApplications,
  listPortalInsuranceCategories,
  listPortalProducts,
  startApplication,
  type ApplicationListItem,
} from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import type { NamedMasterData } from "@/features/system_settings/api";

// An existing application for Product A must never block starting a fresh one for
// Product B — a customer can have any number of independent applications across
// different products. The one thing worth special-casing per product is a Draft
// application for THAT SAME product: continuing it beats silently creating a duplicate.
// There is no backend rule preventing a second same-product application either (none
// exists today) — this is a UX nicety, not an enforced restriction.
//
// Insurance Policy Leads redesign — Apply for Insurance is a two-step flow: pick an
// InsuranceCategory first, then a product within it. Loan stays one step.
export function ProductSelectionPage() {
  const [searchParams] = useSearchParams();
  const category = searchParams.get("category") === "insurance" ? "insurance" : "loan";
  const navigate = useNavigate();
  const [insuranceCategories, setInsuranceCategories] = useState<NamedMasterData[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);
  const [products, setProducts] = useState<NamedMasterData[]>([]);
  const [ownApplications, setOwnApplications] = useState<ApplicationListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState<string | null>(null);

  useEffect(() => {
    setSelectedCategoryId(null);
    setProducts([]);
    listOwnApplications().then(setOwnApplications).catch(() => setOwnApplications([]));
    if (category === "insurance") {
      listPortalInsuranceCategories()
        .then(setInsuranceCategories)
        .catch((err) => setError(getErrorMessage(err)));
    } else {
      listPortalProducts("loan").then(setProducts).catch((err) => setError(getErrorMessage(err)));
    }
  }, [category]);

  useEffect(() => {
    if (category !== "insurance" || !selectedCategoryId) return;
    listPortalProducts("insurance", { insuranceCategoryId: selectedCategoryId })
      .then(setProducts)
      .catch((err) => setError(getErrorMessage(err)));
  }, [category, selectedCategoryId]);

  const onSelect = async (productId: string) => {
    setError(null);
    setIsStarting(productId);
    try {
      const application = await startApplication(category, productId);
      navigate(`/portal/applications/${application.id}`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsStarting(null);
    }
  };

  const productList = (
    <div className="bg-card border border-border rounded-card shadow-card divide-y divide-border">
      {products.length === 0 && <p className="px-4 py-6 text-center text-sm text-text/50">No products available yet.</p>}
      {products.map((product) => {
        const draft = ownApplications.find(
          (app) => app.product_category === category && app.product_id === product.id && app.status === "draft",
        );
        return (
          <button
            key={product.id}
            type="button"
            disabled={isStarting === product.id}
            onClick={() => (draft ? navigate(`/portal/applications/${draft.id}`) : onSelect(product.id))}
            className="w-full text-left px-4 py-3 hover:bg-background disabled:opacity-50 flex items-center justify-between gap-3"
          >
            <div>
              <div className="text-sm text-text">{product.name}</div>
              {product.description && <div className="text-xs text-text/50">{product.description}</div>}
            </div>
            <span className={`shrink-0 text-xs font-medium ${draft ? "text-primary" : "text-text/40"}`}>
              {isStarting === product.id ? "Starting…" : draft ? "Continue Application →" : "Apply Now →"}
            </span>
          </button>
        );
      })}
    </div>
  );

  if (category === "insurance" && !selectedCategoryId) {
    return (
      <div className="max-w-xl">
        <h1 className="text-xl font-semibold text-text mb-4">Choose an insurance category</h1>
        <ErrorBanner message={error} />
        <div className="bg-card border border-border rounded-card shadow-card divide-y divide-border">
          {insuranceCategories.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-text/50">No insurance categories available yet.</p>
          )}
          {insuranceCategories.map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => setSelectedCategoryId(cat.id)}
              className="w-full text-left px-4 py-3 hover:bg-background flex items-center justify-between gap-3"
            >
              <div>
                <div className="text-sm text-text">{cat.name}</div>
                {cat.description && <div className="text-xs text-text/50">{cat.description}</div>}
              </div>
              <span className="shrink-0 text-xs font-medium text-text/40">Select →</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-xl">
      {category === "insurance" && selectedCategoryId ? (
        <button
          type="button"
          onClick={() => setSelectedCategoryId(null)}
          className="mb-3 text-sm text-text/60 hover:text-primary"
        >
          ← All categories
        </button>
      ) : null}
      <h1 className="text-xl font-semibold text-text mb-4 capitalize">Choose a {category} product</h1>
      <ErrorBanner message={error} />
      {productList}
    </div>
  );
}
