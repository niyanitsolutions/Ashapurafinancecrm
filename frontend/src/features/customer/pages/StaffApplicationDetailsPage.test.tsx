import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StaffApplicationDetailsPage } from "./StaffApplicationDetailsPage";
import type { ApplicationDetail, ApplicationDocument } from "@/features/customer/api";

// Regression tests for the "Document Collection → View Full Application → Back"
// navigation-context fix. Root cause: this page always hardcoded
// `backTo="/applications"`, so leaving it from the Leads → Document Collection workflow
// dropped the staff user into the separate Customer Applications module instead of
// back where they started. The fix reads an explicit `?from=document-collection` query
// param (set only by the two Document Collection entry points) and computes the Back
// destination/label from it — every other entry point (Customer Applications module,
// Customer Details page) passes no such param and keeps the original default.

const mockApplication: ApplicationDetail = {
  id: "app-1",
  application_code: "AFS-APP-000010",
  customer_id: "cust-1",
  customer_name: "Test Customer",
  lead_id: "lead-1",
  product_category: "loan",
  product_id: "prod-1",
  product_name: "Personal Loan",
  assigned_to: null,
  assigned_to_name: null,
  status: "submitted",
  created_at: "2026-01-01T00:00:00Z",
  submitted_at: "2026-01-01T00:00:00Z",
  progress_percent: 100,
  case_id: null,
  case_type: null,
  case_code: null,
  case_status: null,
  case_status_label: null,
  form_definition_id: "form-1",
  form_data: {},
  updated_at: "2026-01-01T00:00:00Z",
};

const mockDocuments: ApplicationDocument[] = [];

vi.mock("@/features/customer/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/customer/api")>("@/features/customer/api");
  return {
    ...actual,
    getApplication: vi.fn(() => Promise.resolve(mockApplication)),
    listDocuments: vi.fn(() => Promise.resolve(mockDocuments)),
  };
});

vi.mock("@/features/auth/useAuth", () => ({
  useAuth: () => ({ role: "employee" }),
}));

vi.mock("@/features/customer/useProductSchema", () => ({
  useProductSchema: () => ({
    data: {
      id: "form-1", product_category: "loan", product_id: "prod-1", product_name: "Personal Loan",
      fields: [], required_documents: [], repeatable_groups: [], status: "active", version: 1,
      created_by: null, created_at: "", updated_at: "",
    },
  }),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/applications/:applicationId" element={<StaffApplicationDetailsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// Renders with a real destination route mounted too, so clicking Back can be verified to
// actually land on Document Collection (not just checked via the link's href attribute).
function renderWithDocumentCollectionDestination(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/applications/:applicationId" element={<StaffApplicationDetailsPage />} />
        <Route path="/leads/document-collection" element={<div>Document Collection Records</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("StaffApplicationDetailsPage navigation context", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("opened from Document Collection: Back returns to /leads/document-collection with context-aware label", async () => {
    renderAt("/applications/app-1?from=document-collection");

    const backLink = await screen.findByRole("link", { name: "← Back to Document Collection" });
    expect(backLink).toHaveAttribute("href", "/leads/document-collection");

    // The correct application still loads and renders (documents/actions untouched).
    expect(await screen.findByText("AFS-APP-000010")).toBeInTheDocument();
  });

  it("opened without a from param (e.g. the Customer Applications module): Back keeps the original default", async () => {
    renderAt("/applications/app-1");

    const backLink = await screen.findByRole("link", { name: "← Back" });
    expect(backLink).toHaveAttribute("href", "/applications");
  });

  it("an unrecognized from value falls back to the default Back destination", async () => {
    renderAt("/applications/app-1?from=something-else");

    const backLink = await screen.findByRole("link", { name: "← Back" });
    expect(backLink).toHaveAttribute("href", "/applications");
  });

  it("clicking Back actually navigates to Document Collection, not the Applications module", async () => {
    const user = userEvent.setup();
    renderWithDocumentCollectionDestination("/applications/app-1?from=document-collection");

    const backLink = await screen.findByRole("link", { name: "← Back to Document Collection" });
    await user.click(backLink);

    expect(await screen.findByText("Document Collection Records")).toBeInTheDocument();
  });

  it("survives a fresh mount (equivalent to a page refresh) with the query param intact", async () => {
    // A query param — unlike router state — is part of the URL itself, so a fresh mount
    // (what a real browser refresh produces) re-reads the same `from` value.
    const { unmount } = renderAt("/applications/app-1?from=document-collection");
    await screen.findByRole("link", { name: "← Back to Document Collection" });
    unmount();

    renderAt("/applications/app-1?from=document-collection");
    expect(await screen.findByRole("link", { name: "← Back to Document Collection" })).toHaveAttribute(
      "href",
      "/leads/document-collection",
    );
  });
});
