// Single source of truth for displaying/interpreting business dates and times as India
// Standard Time (Asia/Kolkata) — the CRM's business timezone, regardless of the backend
// server's or the viewing browser's own timezone. See docs/TIMEZONE.md.
//
// Backend timestamps arrive as UTC ISO strings (with an explicit offset — see
// app/config/database.py's tz_aware=True). A bare `new Date(iso).toLocaleString()`
// formats using the *browser's* local timezone, which silently produces the wrong wall
// clock for any viewer not physically in India (and is inconsistent even for one who
// is, once daylight-saving-observing browsers are involved). Every business date/time
// display in this app should go through these functions instead of a fresh
// `Intl.DateTimeFormat`/`toLocaleString` call.
//
// No date library dependency — native `Intl.DateTimeFormat` with `timeZone` already
// does exactly what's needed.

const IST_TIME_ZONE = "Asia/Kolkata";
const IST_UTC_OFFSET_MINUTES = 5 * 60 + 30; // fixed +05:30 — India observes no DST

const _dateTimeFormatter = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST_TIME_ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: true,
});

const _dateFormatter = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST_TIME_ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const _timeFormatter = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hour12: true,
});

const _dateKeyFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: IST_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** "17 Aug 2026, 12:38 PM" */
export function formatISTDateTime(iso: string): string {
  return _dateTimeFormatter.format(new Date(iso));
}

/** "17 Aug 2026" */
export function formatISTDate(iso: string): string {
  return _dateFormatter.format(new Date(iso));
}

/** "12:38 PM" */
export function formatISTTime(iso: string): string {
  return _timeFormatter.format(new Date(iso));
}

function _formatDateKey(date: Date): string {
  const parts = _dateKeyFormatter.formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

const _hourFormatter = new Intl.DateTimeFormat("en-GB", { timeZone: IST_TIME_ZONE, hour: "numeric", hourCycle: "h23" });

/** The current hour (0-23) in IST — for business-hours-dependent UI (e.g. a "Good
 * morning"/"Good afternoon" greeting that should reflect India business hours
 * regardless of which timezone the viewer's own browser is in). */
export function currentISTHour(): number {
  return Number(_hourFormatter.format(new Date()));
}

/** The IST calendar date ("YYYY-MM-DD") for a given instant, or "now" if omitted —
 * for day-bucketing (Today/Yesterday/Earlier) and date-input defaults. */
export function istDateKey(iso?: string): string {
  return _formatDateKey(iso ? new Date(iso) : new Date());
}

/** "YYYY-MM-DD" for the current IST calendar date — e.g. a new Employee's default
 * joining date, so it doesn't read "yesterday" during the first 5.5 hours of the IST
 * day when the underlying clock is UTC-based. */
export function todayISTDateString(): string {
  return istDateKey();
}

/** Converts a user-entered wall-clock date/time (from a `type="date"`/`type="time"`/
 * `type="datetime-local"` input, e.g. dateStr="2026-08-17", timeStr="14:30") — meant as
 * IST regardless of the entering user's own browser timezone — into the correct UTC
 * instant to send to the backend. Fixed +05:30 offset is safe: India observes no DST. */
export function istWallClockToUtcISO(dateStr: string, timeStr: string): string {
  const [year, month, day] = dateStr.split("-").map(Number);
  const [hour, minute] = timeStr.split(":").map(Number);
  const utcMillis = Date.UTC(year, month - 1, day, hour, minute) - IST_UTC_OFFSET_MINUTES * 60 * 1000;
  return new Date(utcMillis).toISOString();
}
