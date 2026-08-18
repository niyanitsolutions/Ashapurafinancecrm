import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { listOwnApplications, listPortalProducts, startApplication, type ApplicationListItem } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import type { NamedMasterData } from "@/features/system_settings/api";

// An existing application for Product A must never block starting a fresh one for
// Product B — a customer can have any number of independent applications across
// different products. The one thing worth special-casing per product is a Draft
// application for THAT SAME product: continuing it beats silently creating a duplicate.
// There is no backend rule preventing a second same-product application either (none
// exists today) — this is a UX nicety, not an enforced restriction.
export function ProductSelectionPage() {
  const [searchParams] = useSearchParams();
  const category = searchParams.get("category") === "insurance" ? "insurance" : "loan";
  const navigate = useNavigate();
  const [products, setProducts] = useState<NamedMasterData[]>([]);
  const [ownApplications, setOwnApplications] = useState<ApplicationListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState<string | null>(null);

  useEffect(() => {
    listPortalProducts(category).then(setProducts).catch((err) => setError(getErrorMessage(err)));
    listOwnApplications().then(setOwnApplications).catch(() => setOwnApplications([]));
  }, [category]);

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

  return (
    <div className="max-w-xl">
      <h1 className="text-xl font-semibold text-text mb-4 capitalize">Choose a {category} product</h1>
      <ErrorBanner message={error} />
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
    </div>
  );
}
