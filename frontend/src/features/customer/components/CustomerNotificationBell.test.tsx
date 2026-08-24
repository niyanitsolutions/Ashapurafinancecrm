import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CustomerNotificationBell } from "./CustomerNotificationBell";
import type { AppNotification } from "@/features/reminders/api";

const rejectedNotification: AppNotification = {
  id: "notif-1",
  notification_type: "document_rejected",
  category: "document",
  title: "Document Rejected",
  message: "Your PAN Card was rejected. Blurry scan.",
  entity_type: "application",
  entity_id: "app-1",
  status: "unread",
  created_at: "2026-01-01T00:00:00Z",
  read_at: null,
};

const { getUnreadNotificationCount, listNotifications, markNotificationRead } = vi.hoisted(() => ({
  getUnreadNotificationCount: vi.fn(() => Promise.resolve(1)),
  listNotifications: vi.fn(() => Promise.resolve({ data: [rejectedNotification], pagination: { total: 1 } })),
  markNotificationRead: vi.fn(() => Promise.resolve(rejectedNotification)),
}));

vi.mock("@/features/reminders/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/reminders/api")>("@/features/reminders/api");
  return { ...actual, getUnreadNotificationCount, listNotifications, markNotificationRead };
});

function renderBell() {
  return render(
    <MemoryRouter>
      <CustomerNotificationBell />
    </MemoryRouter>,
  );
}

describe("CustomerNotificationBell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getUnreadNotificationCount.mockResolvedValue(1);
    listNotifications.mockResolvedValue({ data: [rejectedNotification], pagination: { total: 1 } });
    markNotificationRead.mockResolvedValue(rejectedNotification);
  });

  it("shows the unread count badge from the real unread-count endpoint", async () => {
    renderBell();
    await waitFor(() => expect(getUnreadNotificationCount).toHaveBeenCalled());
    expect(await screen.findByText("1")).toBeInTheDocument();
  });

  it("does not show a badge when there are no unread notifications", async () => {
    getUnreadNotificationCount.mockResolvedValue(0);
    renderBell();
    await waitFor(() => expect(getUnreadNotificationCount).toHaveBeenCalled());
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("opens the dropdown and shows recent notifications on click", async () => {
    const user = userEvent.setup();
    renderBell();
    await user.click(screen.getByRole("button", { name: "Notifications" }));

    expect(await screen.findByText("Document Rejected")).toBeInTheDocument();
    expect(screen.getByText(/Your PAN Card was rejected/)).toBeInTheDocument();
  });

  it("clicking a notification marks it read via the existing mechanism", async () => {
    const user = userEvent.setup();
    renderBell();
    await user.click(screen.getByRole("button", { name: "Notifications" }));
    await screen.findByText("Document Rejected");

    await user.click(screen.getByText("Document Rejected"));
    expect(markNotificationRead).toHaveBeenCalledWith("notif-1");
  });

  it("links straight to the Document Center for a rejection notification", async () => {
    const user = userEvent.setup();
    renderBell();
    await user.click(screen.getByRole("button", { name: "Notifications" }));
    const link = await screen.findByText("Document Rejected");
    expect(link.closest("a")).toHaveAttribute("href", "/portal/documents");
  });

  it("View All links to the dedicated notifications inbox", async () => {
    const user = userEvent.setup();
    renderBell();
    await user.click(screen.getByRole("button", { name: "Notifications" }));
    expect(await screen.findByText("View All")).toHaveAttribute("href", "/portal/alerts");
  });
});
