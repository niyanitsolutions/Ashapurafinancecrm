import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NotificationListPage } from "./NotificationListPage";
import type { AppNotification } from "@/features/reminders/api";

// This exact list component is shared by the Staff Notifications page (/notifications)
// and the Customer Portal's own alerts inbox (/portal/alerts) — the "View" link must
// resolve to the right destination for whichever role is actually looking at it.

let mockRole: string | null = "employee";

vi.mock("@/features/auth/useAuth", () => ({
  useAuth: () => ({ role: mockRole }),
}));

const applicationNotification: AppNotification = {
  id: "notif-1", notification_type: "document_rejected", category: "document", title: "Document Rejected",
  message: "Your PAN Card was rejected.", entity_type: "application", entity_id: "app-1",
  status: "unread", created_at: "2026-01-01T00:00:00Z", read_at: null,
};

const leadNotification: AppNotification = {
  id: "notif-2", notification_type: "lead_assigned", category: "assignment", title: "New Lead Assigned",
  message: "You have been assigned a new lead.", entity_type: "lead", entity_id: "lead-1",
  status: "unread", created_at: "2026-01-01T00:00:00Z", read_at: null,
};

const { listNotifications } = vi.hoisted(() => ({
  listNotifications: vi.fn(() => Promise.resolve({ data: [] as AppNotification[], pagination: { total: 0 } })),
}));

vi.mock("@/features/reminders/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/reminders/api")>("@/features/reminders/api");
  return { ...actual, listNotifications };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <NotificationListPage />
    </MemoryRouter>,
  );
}

describe("NotificationListPage — role-aware View link for application-related notifications", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("staff sees a View link to the Staff Application Details page", async () => {
    mockRole = "employee";
    listNotifications.mockResolvedValue({ data: [applicationNotification], pagination: { total: 1 } });
    renderPage();

    const link = await screen.findByRole("link", { name: "View" });
    expect(link).toHaveAttribute("href", "/applications/app-1");
  });

  it("owner sees the same Staff Application Details destination", async () => {
    mockRole = "owner";
    listNotifications.mockResolvedValue({ data: [applicationNotification], pagination: { total: 1 } });
    renderPage();

    const link = await screen.findByRole("link", { name: "View" });
    expect(link).toHaveAttribute("href", "/applications/app-1");
  });

  it("customer sees a View link to the Document Center instead", async () => {
    mockRole = "customer";
    listNotifications.mockResolvedValue({ data: [applicationNotification], pagination: { total: 1 } });
    renderPage();

    const link = await screen.findByRole("link", { name: "View" });
    expect(link).toHaveAttribute("href", "/portal/documents");
  });

  it("does not show a View link for a notification with no application entity", async () => {
    mockRole = "employee";
    listNotifications.mockResolvedValue({ data: [leadNotification], pagination: { total: 1 } });
    renderPage();

    await screen.findByText("New Lead Assigned");
    expect(screen.queryByRole("link", { name: "View" })).not.toBeInTheDocument();
  });
});
