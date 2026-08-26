import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { MoveApplicationToLoanManagementModal } from "./MoveApplicationToLoanManagementModal";
import type { LeadListItem } from "@/features/leads/api";

const getLeadLessApplicationSummary = vi.fn();
const moveLeadLessApplicationToLoanManagement = vi.fn((_id: string) => Promise.resolve(null));

vi.mock("@/features/leads/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/leads/api")>("@/features/leads/api");
  return {
    ...actual,
    getLeadLessApplicationSummary: (id: string) => getLeadLessApplicationSummary(id),
    moveLeadLessApplicationToLoanManagement: (id: string) => moveLeadLessApplicationToLoanManagement(id),
  };
});

const lead: LeadListItem = {
  id: "app-1", lead_code: "AFS-APP-000001", full_name: "Direct Applicant", mobile: "9611170001", email: null,
  source_id: "", source_name: "Direct", product_category: "loan", product_id: "prod-1", product_name: "Personal Loan",
  assigned_to: null, assigned_to_name: null, status: "pending", stage: "document_collection",
  salary_in_hand: null, next_follow_up_date: null, assigned_by: null, assigned_by_name: null, assigned_at: null,
  rejected_reason: null, rejected_by: null, rejected_by_name: null, rejected_at: null,
  application_id: "app-1", application_status: "submitted", is_potential_duplicate: false, created_at: "2026-08-20T10:00:00Z",
  is_lead_less: true,
};

describe("MoveApplicationToLoanManagementModal", () => {
  it("disables Move to Loan Management while required documents are unverified, and shows the count", async () => {
    getLeadLessApplicationSummary.mockResolvedValueOnce({
      application_id: "app-1", application_status: "submitted", documents_required: 2, documents_verified: 1, all_documents_verified: false,
    });
    render(
      <MemoryRouter>
        <MoveApplicationToLoanManagementModal lead={lead} onClose={vi.fn()} onChanged={vi.fn()} />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getAllByText((_, el) => /1 of 2 required documents verified/.test(el?.textContent ?? "")).length).toBeGreaterThan(0),
    );
    expect(screen.getByRole("button", { name: /move to loan management/i })).toBeDisabled();
    expect(moveLeadLessApplicationToLoanManagement).not.toHaveBeenCalled();
  });

  it("enables the button once all required documents are verified, and calls the move API + onChanged/onClose on click", async () => {
    getLeadLessApplicationSummary.mockResolvedValueOnce({
      application_id: "app-1", application_status: "submitted", documents_required: 2, documents_verified: 2, all_documents_verified: true,
    });
    const onChanged = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <MoveApplicationToLoanManagementModal lead={lead} onClose={onClose} onChanged={onChanged} />
      </MemoryRouter>,
    );

    const button = await screen.findByRole("button", { name: /move to loan management/i });
    expect(button).toBeEnabled();

    await user.click(button);

    await waitFor(() => expect(moveLeadLessApplicationToLoanManagement).toHaveBeenCalledWith("app-1"));
    expect(onChanged).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("stays disabled before the application has been submitted", async () => {
    getLeadLessApplicationSummary.mockResolvedValueOnce({
      application_id: "app-1", application_status: "draft", documents_required: 1, documents_verified: 0, all_documents_verified: false,
    });
    render(
      <MemoryRouter>
        <MoveApplicationToLoanManagementModal lead={lead} onClose={vi.fn()} onChanged={vi.fn()} />
      </MemoryRouter>,
    );

    await screen.findByText(/must submit their application/i);
    expect(screen.getByRole("button", { name: /move to loan management/i })).toBeDisabled();
  });
});
