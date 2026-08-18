import { useRef, useState } from "react";
import { Icon } from "@/theme/icons";

function extensionOf(fileName: string): string {
  const parts = fileName.split(".");
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : "";
}

// The one reusable upload widget in the app (`components/uploads/` was empty before this)
// — drag-and-drop + click-to-browse, and the frontend half of "validate on frontend AND
// backend, never rely only on frontend": rejects an obviously-bad file locally with a
// clear message instead of silently uploading it and waiting for the backend's own
// (authoritative) allowed_types/max_size_mb check to bounce it.
export function FileDropZone({
  accept,
  maxSizeBytes,
  onFile,
  disabled = false,
  label = "Drag & drop, or",
  compact = false,
  compactLabel = "Re-upload",
}: {
  accept?: string[] | null;
  maxSizeBytes?: number | null;
  onFile: (file: File) => void;
  disabled?: boolean;
  label?: string;
  // `compact`: a plain click-to-browse link instead of the full dashed dropzone — for
  // "re-upload"/"add another" affordances next to an already-uploaded document, where
  // the full-size drop target would be visually heavier than the action warrants. Same
  // validation either way.
  compact?: boolean;
  compactLabel?: string;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validate = (file: File): string | null => {
    if (accept && accept.length > 0 && !accept.map((t) => t.toLowerCase()).includes(extensionOf(file.name))) {
      return `File type not allowed. Allowed: ${accept.join(", ").toUpperCase()}`;
    }
    if (maxSizeBytes && file.size > maxSizeBytes) {
      return `File exceeds the maximum size of ${(maxSizeBytes / (1024 * 1024)).toFixed(0)}MB.`;
    }
    return null;
  };

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    const validationError = validate(file);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    onFile(file);
  };

  const hiddenInput = (
    <input
      ref={inputRef}
      type="file"
      className="hidden"
      disabled={disabled}
      accept={accept?.length ? accept.map((t) => `.${t}`).join(",") : undefined}
      onChange={(e) => {
        handleFile(e.target.files?.[0]);
        e.target.value = "";
      }}
    />
  );

  if (compact) {
    return (
      <div>
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="text-primary hover:underline text-xs font-medium disabled:opacity-40 disabled:no-underline"
        >
          {compactLabel}
        </button>
        {hiddenInput}
        {error && <p className="mt-1 text-xs text-danger">{error}</p>}
      </div>
    );
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) inputRef.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (!disabled) handleFile(e.dataTransfer.files?.[0]);
        }}
        className={`flex flex-col items-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-5 text-center text-xs transition-colors ${
          disabled ? "cursor-not-allowed border-border/60 text-text/30" : "cursor-pointer border-border text-text/60 hover:border-primary hover:text-primary"
        } ${isDragging ? "border-primary bg-primary/5 text-primary" : ""}`}
      >
        <Icon name="upload" className="h-5 w-5" />
        <span>
          {label} <span className="font-medium text-primary">choose a file</span>
        </span>
        {(accept?.length || maxSizeBytes) && (
          <span className="text-text/40">
            {accept?.length ? `Allowed: ${accept.join(", ").toUpperCase()}` : ""}
            {accept?.length && maxSizeBytes ? " · " : ""}
            {maxSizeBytes ? `Max ${(maxSizeBytes / (1024 * 1024)).toFixed(0)}MB` : ""}
          </span>
        )}
      </div>
      {hiddenInput}
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
