import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { NotificationBell } from "./NotificationBell";

const { read } = vi.hoisted(() => ({ read: vi.fn(() => Promise.resolve({})) }));
vi.mock("@/features/reminders/api", () => ({
  getUnreadNotificationCount: () => Promise.resolve({ unread_count: 2 }),
  markNotificationRead: read,
  listNotifications: () => Promise.resolve({ data: [
    { id: "n1", title: "New Lead Assigned", message: "Vijay", status: "unread", entity_type: "lead", entity_id: "lead-42", created_at: "2026-09-23T00:00:00Z" },
    { id: "n2", title: "Legacy reminder", message: "Old", status: "read", entity_type: null, entity_id: null, created_at: "2026-09-23T00:00:00Z" },
  ] }),
}));
function Location() { return <p data-testid="location">{useLocation().pathname}</p>; }

describe("staff notification bell", () => {
  it("opens the exact Lead and marks the notification read", async () => {
    render(<MemoryRouter><NotificationBell /><Location /></MemoryRouter>);
    await userEvent.setup().click(screen.getByRole("button", { name: "Notifications" }));
    const link = await screen.findByRole("link", { name: /New Lead Assigned/ });
    expect(link).toHaveAttribute("href", "/leads/lead-42");
    expect(screen.getByRole("link", { name: /Legacy reminder/ })).toHaveAttribute("href", "/notifications");
    await userEvent.setup().click(link);
    await waitFor(() => expect(read).toHaveBeenCalledWith("n1"));
    expect(screen.getByTestId("location")).toHaveTextContent("/leads/lead-42");
  });
});
