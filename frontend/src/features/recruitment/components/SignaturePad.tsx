import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/buttons/Button";
import type { SignatureMethod } from "@/features/recruitment/api";

// Hand-rolled signature capture — no external dependency. Exactly one representation is
// ever "active": switching method clears whatever the previous method produced, so the
// parent form never holds two conflicting signatures.
export interface SignatureValue {
  method: SignatureMethod;
  // draw/upload: a Blob to upload. type: the typed string.
  blob?: Blob;
  text?: string;
  fileName?: string;
  // A local object URL / data URL for previewing an existing or freshly captured image.
  previewUrl?: string;
}

const METHODS: { key: SignatureMethod; label: string }[] = [
  { key: "draw", label: "Draw" },
  { key: "type", label: "Type" },
  { key: "upload", label: "Upload" },
];

export function SignaturePad({
  value,
  existingPreviewUrl,
  onChange,
}: {
  value: SignatureValue | null;
  existingPreviewUrl?: string | null;
  onChange: (value: SignatureValue | null) => void;
}) {
  const [method, setMethod] = useState<SignatureMethod>(value?.method ?? "draw");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawingRef = useRef(false);
  const hasStrokeRef = useRef(false);

  const clearCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    hasStrokeRef.current = false;
  }, []);

  useEffect(() => {
    if (method !== "draw") return;
    clearCanvas();
  }, [method, clearCanvas]);

  const switchMethod = (next: SignatureMethod) => {
    if (next === method) return;
    setMethod(next);
    onChange(null); // dropping the previous method's value — only one active representation
  };

  const pointerPos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const startDraw = (e: React.PointerEvent<HTMLCanvasElement>) => {
    drawingRef.current = true;
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const { x, y } = pointerPos(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const moveDraw = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) return;
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const { x, y } = pointerPos(e);
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#111827";
    ctx.lineTo(x, y);
    ctx.stroke();
    hasStrokeRef.current = true;
  };

  const endDraw = () => {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    const canvas = canvasRef.current;
    if (!canvas || !hasStrokeRef.current) return;
    canvas.toBlob((blob) => {
      if (blob) onChange({ method: "draw", blob, fileName: "signature.png", previewUrl: canvas.toDataURL() });
    }, "image/png");
  };

  const onType = (text: string) => {
    onChange(text.trim() ? { method: "type", text } : null);
  };

  const onUpload = (file: File | undefined) => {
    if (!file) {
      onChange(null);
      return;
    }
    onChange({ method: "upload", blob: file, fileName: file.name, previewUrl: URL.createObjectURL(file) });
  };

  const preview = value?.previewUrl ?? existingPreviewUrl ?? null;

  return (
    <div>
      <div className="mb-2 flex gap-2">
        {METHODS.map((m) => (
          <button
            key={m.key}
            type="button"
            onClick={() => switchMethod(m.key)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
              method === m.key
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-textSecondary hover:bg-background"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {method === "draw" && (
        <div className="space-y-2">
          <canvas
            ref={canvasRef}
            width={440}
            height={140}
            aria-label="Signature drawing area"
            onPointerDown={startDraw}
            onPointerMove={moveDraw}
            onPointerUp={endDraw}
            onPointerLeave={endDraw}
            className="w-full touch-none rounded-xl border border-border bg-card"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              clearCanvas();
              onChange(null);
            }}
          >
            Clear
          </Button>
        </div>
      )}

      {method === "type" && (
        <input
          type="text"
          defaultValue={value?.method === "type" ? value.text : ""}
          onChange={(e) => onType(e.target.value)}
          placeholder="Type your full name"
          aria-label="Typed signature"
          className="w-full rounded-xl border border-border px-3.5 py-2.5 font-signature text-2xl text-text focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          style={{ fontFamily: "'Segoe Script', 'Brush Script MT', cursive" }}
        />
      )}

      {method === "upload" && (
        <div className="space-y-2">
          <input
            type="file"
            accept="image/*"
            aria-label="Upload signature image"
            onChange={(e) => onUpload(e.target.files?.[0])}
            className="block w-full text-sm text-textSecondary file:mr-3 file:rounded-lg file:border-0 file:bg-primary/10 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-primary"
          />
          {preview && method === "upload" && (
            <img src={preview} alt="Signature preview" className="max-h-24 rounded-lg border border-border" />
          )}
        </div>
      )}

      {method === "draw" && preview && (
        <img src={preview} alt="Signature preview" className="mt-2 max-h-24 rounded-lg border border-border" />
      )}
    </div>
  );
}
