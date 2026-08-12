import { useQuery } from "@tanstack/react-query";
import { getFormDefinition, type FormDefinition } from "@/features/customer/api";

// The single shared read-path onto the Product Schema Engine — Employee Create Lead,
// Referral Partner Add Lead, and the Customer Application flow all call this same hook
// for the same product, so there is exactly one place that ever fetches/caches a form
// definition. React Query dedupes concurrent calls and caches by (category, productId),
// so switching back to a previously-viewed product never re-fetches unnecessarily.
export function useProductSchema(productCategory: string | undefined, productId: string | undefined) {
  return useQuery<FormDefinition>({
    queryKey: ["product-schema", productCategory, productId],
    queryFn: () => getFormDefinition(productCategory as string, productId as string),
    enabled: Boolean(productCategory && productId),
    staleTime: 5 * 60_000,
  });
}
