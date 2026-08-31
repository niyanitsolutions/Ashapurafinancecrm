import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TopUpSchedulingModal } from "./TopUpSchedulingModal";

// Top Up Loan (production add-on) — one popup reused by every entry point (Disbursed
// list's "Top Up", the automatic popup right after disbursing, and the Top Up Loan
// list's "Rejected"/reschedule). Covers: the calculated eligibility date is derived
// from the case's own stored disbursed_at (never "today"), Custom shows/validates a
// date field, "No" schedules nothing, and Submit calls the real API with the right
// payload and reports success back to the caller.

const getLoanCase = vi.fn((_id: string) =>
  Promise.resolve({
    id: "case-1", case_code: "AFS-LOAN-000015", customer: { full_name: "dummy lead" }, customer_name: "dummy lead",
    loan_details: { disbursed_at: "2026-08-25T04:00:00.000Z" },
  }),
);
const scheduleTopUp = vi.fn((_id: string, _payload: Record<string, unknown>) => Promise.resolve({}));

vi.mock("@/features/loan_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/loan_management/api")>("@/features/loan_management/api");
  return {
    ...actual,
    getLoanCase: (id: string) => getLoanCase(id),
    scheduleTopUp: (id: string, payload: Record<string, unknown>) => scheduleTopUp(id, payload),
  };
});

function hasText(text: string) {
  return (_: string, el: Element | null) => Boolean(el?.textContent?.includes(text));
}

function renderModal(onScheduled = vi.fn(), onClose = vi.fn()) {
  return { onScheduled, onClose, ...render(<TopUpSchedulingModal caseId="case-1" onClose={onClose} onScheduled={onScheduled} />) };
}

describe("TopUpSchedulingModal", () => {
  it("shows the customer/case/disbursed date fetched from the backend, not a client-guessed value", async () => {
    renderModal();
    await waitFor(() => expect(screen.getAllByText(hasText("dummy lead")).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText(hasText("AFS-LOAN-000015")).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText(hasText("25-Aug-2026")).length).toBeGreaterThan(0));
  });

  it("selecting 3 Months shows the calculated eligibility date (calendar months, not a fixed day count)", async () => {
    const user = userEvent.setup();
    renderModal();
    await screen.findByLabelText("3 Months");
    await user.click(screen.getByLabelText("3 Months"));
    // 25 Aug 2026 + 3 calendar months = 25 Nov 2026.
    await waitFor(() => expect(screen.getAllByText(hasText("25-Nov-2026")).length).toBeGreaterThan(0));
  });

  it("selecting Custom reveals a date field; a date before disbursement is rejected client-side", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(await screen.findByLabelText("Custom"));
    const dateInput = await screen.findByLabelText(/custom eligibility date/i);
    await user.type(dateInput, "2026-08-20");

    expect(screen.getByText(/cannot be earlier than the disbursed date/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
  });

  it("a valid Custom date is accepted and enables Submit", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(await screen.findByLabelText("Custom"));
    await user.type(await screen.findByLabelText(/custom eligibility date/i), "2026-12-15");

    expect(screen.queryByText(/cannot be earlier than the disbursed date/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit/i })).toBeEnabled();
  });

  it("selecting No does not require a date and submits with period 'no'", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(await screen.findByLabelText("No"));
    expect(screen.getByRole("button", { name: /submit/i })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() => expect(scheduleTopUp).toHaveBeenCalledWith("case-1", { period: "no", custom_date: undefined, remarks: undefined }));
  });

  it("Submit calls the API with the selected period/remarks and reports success to the caller", async () => {
    const onScheduled = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderModal(onScheduled, onClose);

    await user.click(await screen.findByLabelText("6 Months"));
    await user.type(screen.getByLabelText(/remarks/i), "Customer requested a review");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() =>
      expect(scheduleTopUp).toHaveBeenCalledWith("case-1", { period: "6_months", custom_date: undefined, remarks: "Customer requested a review" }),
    );
    await waitFor(() => expect(onScheduled).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  it("Submit is disabled until a period is selected", async () => {
    renderModal();
    await screen.findByLabelText("3 Months");
    expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
  });
});
