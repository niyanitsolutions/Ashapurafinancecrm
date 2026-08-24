import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentRejectionAlert } from "./DocumentRejectionAlert";
import type { AppNotification } from "@/features/reminders/api";

function makeNotification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "notif-1", notification_type: "document_rejected", category: "document", title: "Document Rejected",
    message: "Your PAN Card was rejected. Blurry scan.", entity_type: "application", entity_id: "app-1",
    status: "unread", created_at: "2026-01-01T00:00:00Z", read_at: null,
    ...overrides,
  };
}

const { listNotifications, markNotificationRead } = vi.hoisted(() => ({
  listNotifications: vi.fn(() => Promise.resolve({ data: [] as AppNotification[], pagination: { total: 0 } })),
  markNotificationRead: vi.fn(() => Promise.resolve(makeNotification())),
}));

vi.mock("@/features/reminders/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/reminders/api")>("@/features/reminders/api");
  return { ...actual, listNotifications, markNotificationRead };
});

function renderAlert() {
  return render(
    <MemoryRouter initialEntries={["/portal"]}>
      <Routes>
        <Route path="/portal" element={<DocumentRejectionAlert />} />
        <Route path="/portal/documents" element={<div>Document Center Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("DocumentRejectionAlert", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listNotifications.mockResolvedValue({ data: [], pagination: { total: 0 } });
    markNotificationRead.mockResolvedValue(makeNotification());
  });

  it("shows no popup when there are no unread document_rejected notifications", async () => {
    renderAlert();
    await waitFor(() => expect(listNotifications).toHaveBeenCalled());
    expect(screen.queryByText("Document Requires Attention")).not.toBeInTheDocument();
  });

  it("shows the popup with the rejection message for an unread document_rejected notification", async () => {
    listNotifications.mockResolvedValue({ data: [makeNotification()], pagination: { total: 1 } });
    renderAlert();

    expect(await screen.findByText("Document Requires Attention")).toBeInTheDocument();
    expect(screen.getByText(/Your PAN Card was rejected\. Blurry scan\./)).toBeInTheDocument();
  });

  it("ignores an unread notification that is not a document rejection", async () => {
    listNotifications.mockResolvedValue({
      data: [makeNotification({ notification_type: "support_request_raised", id: "notif-2" })],
      pagination: { total: 1 },
    });
    renderAlert();
    await waitFor(() => expect(listNotifications).toHaveBeenCalled());
    expect(screen.queryByText("Document Requires Attention")).not.toBeInTheDocument();
  });

  it("Upload New Document marks the notification read and navigates to the Document Center", async () => {
    listNotifications.mockResolvedValue({ data: [makeNotification()], pagination: { total: 1 } });
    const user = userEvent.setup();
    renderAlert();
    await screen.findByText("Document Requires Attention");

    await user.click(screen.getByRole("button", { name: "Upload New Document" }));

    expect(markNotificationRead).toHaveBeenCalledWith("notif-1");
    expect(await screen.findByText("Document Center Page")).toBeInTheDocument();
  });

  it("View Later dismisses the popup and marks it read without navigating", async () => {
    listNotifications.mockResolvedValue({ data: [makeNotification()], pagination: { total: 1 } });
    const user = userEvent.setup();
    renderAlert();
    await screen.findByText("Document Requires Attention");

    await user.click(screen.getByRole("button", { name: "View Later" }));

    expect(markNotificationRead).toHaveBeenCalledWith("notif-1");
    await waitFor(() => expect(screen.queryByText("Document Requires Attention")).not.toBeInTheDocument());
    expect(screen.queryByText("Document Center Page")).not.toBeInTheDocument();
  });

  it("queues multiple unread rejections one at a time — dismissing one reveals the next", async () => {
    listNotifications.mockResolvedValue({
      data: [makeNotification({ id: "notif-1", message: "Your PAN Card was rejected." }), makeNotification({ id: "notif-2", message: "Your Salary Slip was rejected." })],
      pagination: { total: 2 },
    });
    const user = userEvent.setup();
    renderAlert();
    await screen.findByText(/PAN Card was rejected/);

    await user.click(screen.getByRole("button", { name: "View Later" }));

    expect(await screen.findByText(/Salary Slip was rejected/)).toBeInTheDocument();
  });
});
