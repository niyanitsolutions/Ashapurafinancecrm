import { useEffect, useRef, useState, type InputHTMLAttributes } from "react";

import { displayDate, parseDate } from "@/shared/dateInput";

export function DateInput({ value, onChange, min, max, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  const [draft,setDraft] = useState(displayDate(String(value || "")));
  const emitted = useRef<string | null>(null);
  useEffect(() => {
    const incoming = String(value || "");
    if (emitted.current === incoming) { emitted.current = null; return; }
    setDraft(displayDate(incoming));
  },[value]);
  return <input {...props} type="text" inputMode="numeric" placeholder="DD/MM/YYYY" pattern="[0-9]{2}/[0-9]{2}/[0-9]{4}" value={draft}
    onChange={event => {
      const text = event.target.value; setDraft(text);
      const iso = parseDate(text);
      const valid = !text || (iso && (!min || iso >= String(min)) && (!max || iso <= String(max)));
      event.target.setCustomValidity(valid ? "" : "Enter a valid date in DD/MM/YYYY format within the allowed range.");
      {
        // The DOM displays DD/MM/YYYY; existing handlers keep receiving canonical ISO dates.
        emitted.current = iso || "";
        const target = { ...event.target, value: emitted.current };
        onChange?.({ ...event, target, currentTarget: target } as typeof event);
      }
    }} />;
}
