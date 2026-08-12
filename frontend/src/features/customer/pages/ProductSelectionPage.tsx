import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { startApplication } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { insuranceProductsApi, loanProductsApi, type NamedMasterData } from "@/features/system_settings/api";

export function ProductSelectionPage() {
  const [searchParams] = useSearchParams();
  const category = searchParams.get("category") === "insurance" ? "insurance" : "loan";
  const navigate = useNavigate();
  const [products, setProducts] = useState<NamedMasterData[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState<string | null>(null);

  useEffect(() => {
    const api = category === "loan" ? loanProductsApi : insuranceProductsApi;
    api.list().then(setProducts).catch((err) => setError(getErrorMessage(err)));
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
        {products.map((product) => (
          <button
            key={product.id}
            type="button"
            disabled={isStarting === product.id}
            onClick={() => onSelect(product.id)}
            className="w-full text-left px-4 py-3 hover:bg-background disabled:opacity-50"
          >
            <div className="text-sm text-text">{product.name}</div>
            {product.description && <div className="text-xs text-text/50">{product.description}</div>}
          </button>
        ))}
      </div>
    </div>
  );
}
