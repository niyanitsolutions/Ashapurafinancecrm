import { ApiError } from "@/shared/api/client";
import { confirmDocument, getDocumentUploadUrl } from "./api";

// Customer-only progress transport; staff keep their existing upload helper unchanged.
export async function uploadCustomerDocument(applicationId: string, typeId: string, file: File,
  password?: string, side?: string, onProgress?: (percent: number) => void) {
  const { upload_url, s3_key } = await getDocumentUploadUrl(applicationId, typeId, file.name, file.type);
  onProgress?.(0);
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", upload_url);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.timeout = 120000;
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) onProgress?.(Math.min(99, Math.round(event.loaded / event.total * 100)));
    };
    const failed = () => reject(new ApiError("document_upload_failed", "Upload was not confirmed. Please check your connection and try again."));
    xhr.onerror = failed; xhr.ontimeout = failed; xhr.onabort = failed;
    xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : failed();
    xhr.send(file);
  });
  const document = await confirmDocument(applicationId, typeId, file.name, s3_key, file.type, password, side);
  onProgress?.(100);
  return document;
}
