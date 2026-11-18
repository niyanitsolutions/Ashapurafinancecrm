import { beforeEach, describe, expect, it, vi } from "vitest";
import { uploadCustomerDocument } from "./customerUpload";
import * as api from "./api";

vi.mock("./api", () => ({ getDocumentUploadUrl: vi.fn(), confirmDocument: vi.fn() }));
const instances: FakeXHR[] = [];
class FakeXHR {
  status = 200;
  timeout = 0;
  upload: { onprogress?: (event: { lengthComputable: boolean; loaded: number; total: number }) => void } = {};
  onload?: () => void;
  onerror?: () => void;
  onabort?: () => void;
  ontimeout?: () => void;
  open = vi.fn();
  setRequestHeader = vi.fn();
  send = vi.fn(() => {
    this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
    this.onload?.();
  });
  constructor() { instances.push(this); }
}
beforeEach(() => {
  instances.length = 0; vi.resetAllMocks(); vi.stubGlobal("XMLHttpRequest", FakeXHR);
  vi.mocked(api.getDocumentUploadUrl).mockResolvedValue({ upload_url: "https://private-storage.example/signed", s3_key: "server-key" });
  vi.mocked(api.confirmDocument).mockResolvedValue({ id: "document" } as api.ApplicationDocument);
});
describe("Customer private upload progress", () => {
  it("uses the presigned PUT, forwards metadata and confirms only after upload", async () => {
    const file = new File(["test"], "test.pdf", { type: "application/pdf" });
    const progress = vi.fn();
    await uploadCustomerDocument("app", "type", file, "fixture-file-password", "front", progress);
    expect(instances.at(-1)!.open).toHaveBeenCalledWith("PUT", "https://private-storage.example/signed");
    expect(instances.at(-1)!.setRequestHeader).toHaveBeenCalledExactlyOnceWith("Content-Type", "application/pdf");
    expect(api.confirmDocument).toHaveBeenCalledWith("app", "type", "test.pdf", "server-key", "application/pdf", "fixture-file-password", "front");
    expect(progress.mock.calls.map(call => call[0])).toEqual([0, 50, 100]);
  });
  it.each(["rejection", "timeout", "connection"])("does not confirm or retry after %s", async failure => {
    class FailedXHR extends FakeXHR {
      send = vi.fn(() => {
        if (failure === "timeout") this.ontimeout?.();
        else if (failure === "connection") this.onerror?.();
        else { this.status = 403; this.onload?.(); }
      });
    }
    vi.stubGlobal("XMLHttpRequest", FailedXHR);
    await expect(uploadCustomerDocument("app", "type", new File(["test"], "test.pdf"))).rejects.toThrow("Upload was not confirmed");
    expect(instances.at(-1)!.send).toHaveBeenCalledOnce(); expect(api.confirmDocument).not.toHaveBeenCalled();
  });
});
