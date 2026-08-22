import { renderHook } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { documentCollectionQuery, useDocumentCollectionBackContext } from "./navigationContext";

// Shared navigation-context contract behind the Document Collection -> Application /
// Loan Case / Insurance Case Details -> Back fix. Every page that reads this hook
// (StaffApplicationDetailsPage, LoanCaseDetailsPage, InsuranceCaseDetailsPage) trusts
// this exact behavior, so it's tested once, here, rather than duplicated per page.
function renderAt(path: string, defaultBackTo: string) {
  return renderHook(() => useDocumentCollectionBackContext(defaultBackTo), {
    wrapper: ({ children }) => (
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/x" element={<>{children}</>} />
        </Routes>
      </MemoryRouter>
    ),
  });
}

describe("useDocumentCollectionBackContext", () => {
  it("returns the default destination with no context param", () => {
    const { result } = renderAt("/x", "/applications");
    expect(result.current.backTo).toBe("/applications");
    expect(result.current.backLabel).toBeUndefined();
    expect(result.current.fromDocumentCollection).toBe(false);
  });

  it("routes to Document Collection when opened with the context param", () => {
    const { result } = renderAt(`/x${documentCollectionQuery()}`, "/loan-cases");
    expect(result.current.backTo).toBe("/leads/document-collection");
    expect(result.current.backLabel).toBe("← Back to Document Collection");
    expect(result.current.fromDocumentCollection).toBe(true);
  });

  it("falls back to the default for an unrecognized from value", () => {
    const { result } = renderAt("/x?from=something-else", "/insurance-cases");
    expect(result.current.backTo).toBe("/insurance-cases");
    expect(result.current.backLabel).toBeUndefined();
    expect(result.current.fromDocumentCollection).toBe(false);
  });

  it("respects each caller's own default destination", () => {
    expect(renderAt("/x", "/applications").result.current.backTo).toBe("/applications");
    expect(renderAt("/x", "/loan-cases").result.current.backTo).toBe("/loan-cases");
    expect(renderAt("/x", "/insurance-cases").result.current.backTo).toBe("/insurance-cases");
  });
});
