import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RecruitmentLeadModal } from "./RecruitmentLeadModal";
import type { RecruitmentLeadDetail } from "@/features/recruitment/api";

const createRecruitmentLead = vi.fn(() => Promise.resolve({ id: "rec-1" } as RecruitmentLeadDetail));
const moveRecruitmentToBop = vi.fn(() => Promise.resolve({} as RecruitmentLeadDetail));

vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return {
    ...actual,
    getRecruitmentLookup: () => Promise.resolve({ sources: [{ id: "src-1", name: "Referral" }] }),
    createRecruitmentLead: (...args: unknown[]) => createRecruitmentLead(...(args as [])),
    moveRecruitmentToBop: (...args: unknown[]) => moveRecruitmentToBop(...(args as [])),
  };
});

function fill(user: ReturnType<typeof userEvent.setup>) {
  return (async () => {
    await user.type(screen.getByLabelText("Name"), "Ravi Kumar");
    await user.type(screen.getByLabelText("Mobile Number"), "9876543210");
    await user.type(screen.getByLabelText("Age"), "32");
    await user.selectOptions(screen.getByLabelText("Gender"), "male");
    await user.selectOptions(screen.getByLabelText("Source"), "src-1");
    await user.selectOptions(screen.getByLabelText("Profession"), "salaried");
  })();
}

describe("RecruitmentLeadModal", () => {
  it("shows the Other Profession field only when profession is Other", async () => {
    const user = userEvent.setup();
    render(<RecruitmentLeadModal mode="create" lead={null} onClose={vi.fn()} onSaved={vi.fn()} />);
    await screen.findByLabelText("Source");

    expect(screen.queryByLabelText("Other Profession")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Profession"), "other");
    expect(screen.getByLabelText("Other Profession")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Profession"), "salaried");
    expect(screen.queryByLabelText("Other Profession")).not.toBeInTheDocument();
  });

  it("Save creates the lead and does not move it to BOP", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    render(<RecruitmentLeadModal mode="create" lead={null} onClose={vi.fn()} onSaved={onSaved} />);
    await screen.findByLabelText("Source");
    await fill(user);

    await user.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(createRecruitmentLead).toHaveBeenCalled());
    expect(moveRecruitmentToBop).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalled();
  });

  it("Save & Move to BOP creates the lead then moves it", async () => {
    const user = userEvent.setup();
    render(<RecruitmentLeadModal mode="create" lead={null} onClose={vi.fn()} onSaved={vi.fn()} />);
    await screen.findByLabelText("Source");
    await fill(user);

    await user.click(screen.getByRole("button", { name: /save & move to bop/i }));
    await waitFor(() => expect(moveRecruitmentToBop).toHaveBeenCalledWith("rec-1"));
  });
});
