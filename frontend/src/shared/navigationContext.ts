import { useSearchParams } from "react-router-dom";

// Shared "opened from Leads -> Document Collection" navigation-context contract — a
// query param (not router state, so it survives a page refresh), read by every staff
// detail page reachable from that workflow: Staff Application Details, Loan Case
// Details, Insurance Case Details. One definition, reused everywhere, so the contract
// (`?from=document-collection`) can never drift between pages.
export const DOCUMENT_COLLECTION_SOURCE = "document-collection";

/** Appended to a `to=` string to carry the Document Collection context forward — e.g.
 * `` `/applications/${id}${documentCollectionQuery()}` ``. */
export function documentCollectionQuery(): string {
  return `?from=${DOCUMENT_COLLECTION_SOURCE}`;
}

/** For a detail page's own Back control. `defaultBackTo` is used whenever the page
 * wasn't opened with the Document Collection context — i.e. every existing entry point
 * (Customer Applications module, Loan/Insurance Management's own case list, Customer
 * Details page) keeps its original, unchanged Back destination. */
export function useDocumentCollectionBackContext(defaultBackTo: string): {
  backTo: string;
  backLabel: string | undefined;
  fromDocumentCollection: boolean;
} {
  const [searchParams] = useSearchParams();
  const fromDocumentCollection = searchParams.get("from") === DOCUMENT_COLLECTION_SOURCE;
  return {
    backTo: fromDocumentCollection ? "/leads/document-collection" : defaultBackTo,
    backLabel: fromDocumentCollection ? "← Back to Document Collection" : undefined,
    fromDocumentCollection,
  };
}
