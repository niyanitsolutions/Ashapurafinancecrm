import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { SupportTicketListPage } from "./SupportTicketListPage";

const { getSupportTicket } = vi.hoisted(() => ({ getSupportTicket: vi.fn() }));
vi.mock("@/features/support/api", () => ({ getSupportTicket, listAllSupportTickets: () => Promise.resolve([]) }));

it("opens the exact support ticket independently of list filters", async () => {
  getSupportTicket.mockResolvedValue({ id: "ticket1", ticket_code: "AFS-TICKET-1", subject: "Pan card", message: "PAN help", status: "open", staff_response: null });
  render(<MemoryRouter initialEntries={["/support-tickets?ticket=ticket1"]}><SupportTicketListPage /></MemoryRouter>);
  expect(await screen.findByRole("dialog", { name: /AFS-TICKET-1/ })).toBeInTheDocument();
  expect(getSupportTicket).toHaveBeenCalledWith("ticket1");
});

it("does not expose a restricted ticket", async () => {
  getSupportTicket.mockRejectedValue(new Error("Forbidden"));
  render(<MemoryRouter initialEntries={["/support-tickets?ticket=restricted"]}><SupportTicketListPage /></MemoryRouter>);
  expect(await screen.findByText("This ticket is unavailable or you do not have access.")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
