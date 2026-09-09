import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EditAdvisorModal } from "./EditAdvisorModal";
import type { AdvisorDetail } from "@/features/recruitment/api";

const updateAdvisor = vi.fn(() => Promise.resolve({} as AdvisorDetail));
vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return { ...actual, updateAdvisor: (...a: unknown[]) => updateAdvisor(...(a as [])) };
});

const advisor: AdvisorDetail = {
  id: "a1",
  advisor_code: "AFS-ADV-000001",
  recruitment_lead_id: "r1",
  full_name: "Ravi Kumar",
  mobile: "9876543210",
  email: null,
  channel: "non_qr",
  agency_code: null,
  agent_code: null,
  status: "active",
  is_employee: false,
  no_of_policies: 0,
  total_premium: 0,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  recruitment: null,
  businesses: [],
};

describe("EditAdvisorModal", () => {
  it("never pre-fills a password and offers a QR / Non QR Type", () => {
    render(<EditAdvisorModal advisor={advisor} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByLabelText("Password")).toHaveValue("");
    const type = screen.getByLabelText("Type") as HTMLSelectElement;
    expect([...type.options].map((o) => o.textContent)).toEqual(["QR", "Non QR"]);
  });

  it("sends only the changed fields (agent code, type, password)", async () => {
    const user = userEvent.setup();
    render(<EditAdvisorModal advisor={advisor} onClose={vi.fn()} onSaved={vi.fn()} />);

    await user.type(screen.getByLabelText("Agent Code"), "AGT-9");
    await user.selectOptions(screen.getByLabelText("Type"), "qr");
    await user.type(screen.getByLabelText("Password"), "S3cretPass!");

    await user.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() =>
      expect(updateAdvisor).toHaveBeenCalledWith("a1", {
        agent_code: "AGT-9",
        channel: "qr",
        password: "S3cretPass!",
      }),
    );
  });
});
