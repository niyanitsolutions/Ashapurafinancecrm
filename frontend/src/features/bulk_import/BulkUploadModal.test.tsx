import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BulkUploadModal, type ImportPreview } from "./BulkUploadModal";

const { apiRequest } = vi.hoisted(() => ({ apiRequest: vi.fn() }));
vi.mock("@/shared/api/client", () => ({ apiRequest }));
vi.mock("@/shared/geolocation", () => ({ getCurrentCoordinates: () => Promise.resolve({}) }));

const batch: ImportPreview = { batch_id: "batch", state: "preview", total: 2, valid: 1, invalid: 1, duplicate: 0, imported: 0, failed: 0, processing: 0,
  rows: [{ number: 2, values: { full_name: "Ramesh", mobile: "9876543210" }, status: "valid", error: "" }, { number: 3, values: { full_name: "Priya" }, status: "invalid", error: "Mobile number is invalid." }] };

function choose(name = "leads.csv", content = "Full Name,Mobile\nRamesh,9876543210") {
  fireEvent.change(screen.getByLabelText("Choose CSV / Excel File"), { target: { files: [new File([content], name, { type: "text/csv" })] } });
}

describe("BulkUploadModal", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("continues checkpointed chunks after a single confirmation", async () => {
    apiRequest.mockResolvedValueOnce(batch)
      .mockResolvedValueOnce({ ...batch, imported: 25, valid: 1 })
      .mockResolvedValueOnce({ ...batch, state: "completed", imported: 26, valid: 0 });
    render(<BulkUploadModal kind="leads" onClose={vi.fn()} onImported={vi.fn()} />);
    choose();
    await userEvent.setup().click(screen.getByRole("button", { name: "Continue" }));
    await userEvent.setup().click(await screen.findByRole("button", { name: "Import 1 Records" }));
    expect(await screen.findByText(/26 leads imported successfully/)).toBeInTheDocument();
    expect(apiRequest).toHaveBeenCalledTimes(3);
  });

  it.each(["leads", "insurance"] as const)("validates %s before explicit confirmation and shows partial results", async (kind) => {
    const user = userEvent.setup();
    const onImported = vi.fn();
    apiRequest.mockResolvedValueOnce(batch).mockResolvedValueOnce({ ...batch, state: "completed", valid: 0, imported: 1 });
    render(<BulkUploadModal kind={kind} onClose={vi.fn()} onImported={onImported} />);
    expect(screen.getByRole("button", { name: "Download Sample Excel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    choose();
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText(/Mobile number is invalid/)).toBeInTheDocument();
    expect(screen.getByText(/Total: 2 · Valid: 1/)).toBeInTheDocument();
    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(apiRequest).toHaveBeenCalledWith(`/bulk-import/${kind}/preview`, expect.objectContaining({ method: "POST", body: expect.any(FormData) }));
    expect(onImported).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Import 1 Records" }));
    expect(await screen.findByText(/1 leads imported successfully/)).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Import 1 Records" })).not.toBeInTheDocument();
  });

  it.each(["bad.xls", "bad.exe", "bad.xlsx"])("validates file type and empty file: %s", async (name) => {
    render(<BulkUploadModal kind="leads" onClose={vi.fn()} onImported={vi.fn()} />);
    choose(name, name.endsWith("xlsx") ? "" : "bad");
    await userEvent.setup().click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText(name.endsWith("xlsx") ? /non-empty file/ : /Choose a CSV or XLSX/)).toBeInTheDocument();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("shows loading and prevents duplicate submissions, then recovers from API failure", async () => {
    let reject!: (error: Error) => void;
    apiRequest.mockReturnValue(new Promise((_resolve, rejectPromise) => { reject = rejectPromise; }));
    render(<BulkUploadModal kind="insurance" onClose={vi.fn()} onImported={vi.fn()} />);
    choose();
    await userEvent.setup().click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Validating file...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    reject(new Error("Unable to process the file."));
    expect(await screen.findByText("Unable to process the file.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled());
  });

  it("downloads the server-generated sample", async () => {
    apiRequest.mockResolvedValue({ filename: "insurance-sample.xlsx", content: btoa("workbook") });
    const create = vi.fn(() => "blob:test");
    vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<BulkUploadModal kind="insurance" onClose={vi.fn()} onImported={vi.fn()} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Download Sample Excel" }));
    await waitFor(() => expect(create).toHaveBeenCalledOnce());
    expect(apiRequest).toHaveBeenCalledWith("/bulk-import/insurance/sample");
    expect(click).toHaveBeenCalledOnce();
    click.mockRestore();
  });

  it("shows empty valid results and allows an error report download", async () => {
    apiRequest.mockResolvedValue({ ...batch, valid: 0, invalid: 2 });
    const create = vi.fn(() => "blob:error-report");
    vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<BulkUploadModal kind="leads" onClose={vi.fn()} onImported={vi.fn()} />);
    choose();
    await userEvent.setup().click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("No valid records found.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import 0 Records" })).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("button", { name: "Download Error Report" }));
    expect(create).toHaveBeenCalledOnce();
    click.mockRestore();
  });
});
