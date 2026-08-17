# Timezone Standardization — IST (Asia/Kolkata)

See `docs/decisions/DECISIONS.md` #124 for the full rationale and file-by-file impact.
This document is the quick reference: what the convention actually is, where the
utilities live, and what's still a known limitation.

## The rule

- **Storage/machine timestamps stay UTC, everywhere.** Mongo documents (`created_at`,
  `updated_at`, ...), JWT `iat`/`exp`, Redis TTLs — all UTC, unchanged by this work.
- **Business dates/times are India Standard Time (Asia/Kolkata)** — "today", "this
  month", a Geo Fence's daily 09:00–18:00 window, a report's date range, what a user
  sees on screen. Configured via `Settings.timezone` (`APP_TIMEZONE=Asia/Kolkata` in
  every `.env*` file), not hardcoded a second time anywhere.
- **MongoDB reads are tz-aware UTC**, not naive. `app/config/database.py`'s
  `get_client()` sets `tz_aware=True` on the Motor client — this is the actual
  root-cause fix for "the frontend shows the wrong clock": a *naive* timestamp
  serialized with no `Z`/offset is parsed by JS `Date` as the *viewer's browser-local*
  time, not UTC. With `tz_aware=True`, every response carries an explicit UTC offset and
  the ambiguity is gone. (`mongomock_motor`, this suite's test double, honors the same
  flag identically — verified directly, not assumed.)

## Backend utility — `app/utils/datetime.py`

| Function | Use for |
|---|---|
| `utc_now()` | Machine timestamps (unchanged, pre-existing) |
| `now_ist()` | "Now" for any business-hour/business-day comparison |
| `to_ist(dt)` | Convert any datetime to IST wall-clock |
| `start_of_day_ist(dt=None)` / `end_of_day_ist(dt=None)` | IST midnight (or next midnight), as a UTC instant — the correct Mongo query bound for "today" |
| `start_of_month_ist(dt=None)` / `ist_month_start_utc(year, month)` | Same, for calendar months |
| `ist_date_range_to_utc_bounds(date_from, date_to)` | Two IST calendar dates (a report/date filter) → `($gte, $lt)` UTC instant bounds |
| `within_daily_window(...)` | Unchanged internals (decision 022/112) — but its `now` argument must already be business-timezone-converted (pass `now_ist()`, never `utc_now()`) |

**Never** call `datetime.now()`/`utc_now()` directly and treat the result as "today" for
a business-facing calculation — route it through the table above.

## Frontend utility — `frontend/src/shared/dateFormat.ts`

No date library dependency — native `Intl.DateTimeFormat` with `timeZone:
"Asia/Kolkata"` does everything needed.

| Function | Use for |
|---|---|
| `formatISTDateTime(iso)` | "17 Aug 2026, 12:38 PM" — the default for any displayed timestamp |
| `formatISTDate(iso)` | "17 Aug 2026" |
| `formatISTTime(iso)` | "12:38 PM" |
| `istDateKey(iso?)` | "YYYY-MM-DD" in IST — day-bucketing (Today/Yesterday/Earlier) |
| `todayISTDateString()` | Today's IST date, for a date-input default |
| `istWallClockToUtcISO(dateStr, timeStr)` | A user-entered `date`/`time`/`datetime-local` value, meant as IST, → the correct UTC instant to send to the backend |
| `currentISTHour()` | India business hour (0-23), for hour-dependent UI (e.g. a greeting) |

**Never** display a backend timestamp with a bare `new Date(iso).toLocaleString()`/
`.toLocaleDateString()` (uses the *viewer's* browser timezone) — use the table above.
**Never** convert a `type="date"`/`"time"`/`"datetime-local"` input value through
`new Date(value).toISOString()` before sending it to the backend unless the value
already carries a `Z`/offset — that silently reinterprets it as browser-local time.

## Deliberately left alone (timezone-agnostic by construction)

Duration/absolute-instant comparisons need no IST conversion — converting them would be
a no-op at best and a bug at worst:
- JWT `exp`/`iat`, Redis TTLs (OTP expiry, lockout windows) — durations, not wall-clock.
- `check_task_reminders`/`check_re_eligible_cases` (`worker/tasks/reminders.py`) — every
  comparison is `now < some_instant`, never a calendar-day boundary.
- `check_commission_triggers`/`refresh_meta_tokens` — re-scan by *status*, not by date.
- Frontend: `RecentActivitiesCard`'s relative-time ("5m ago") math, `TaskOverviewRow`'s
  overdue check, `GenerateLinkModal`'s expiry comparison, `ApplicationPage`'s local
  "saved Xs ago" indicator — all `Date.now() - instant` or `instant < Date.now()`.

## Known limitation: arq cron trigger hours

`worker_settings.py`'s three fixed-hour daily jobs (`check_re_eligible_cases` @ 2am,
`check_commission_triggers` @ 3am, `refresh_meta_tokens` @ 4am) rely on arq's
`cron(hour=..., minute=...)`, which matches the **worker process's own OS wall-clock** —
arq has no tz-aware cron primitive, so this app cannot make the trigger hour itself
IST-aware without deeper surgery (e.g. wrapping each job in its own IST-based
self-gating with a tracked last-run date). This is disclosed as a known, low-risk
limitation rather than solved: these are internal maintenance batches with no
user-facing "must fire at exactly 2am IST" promise, and (confirmed by reading each) none
of their own business decisions are calendar-day-boundary comparisons — see the table
above. The configured hours assume the deployed worker process's OS clock is UTC (this
app's documented default). If that assumption is ever wrong, only the *time of day*
these three jobs run shifts — not their correctness.

## Runtime dependency: `tzdata`

`zoneinfo.ZoneInfo("Asia/Kolkata")` has no bundled IANA database on Windows, and on
minimal Linux container images (e.g. `python:3.12-slim`) that don't ship
`/usr/share/zoneinfo`. `tzdata` (the official CPython-maintained PyPI package for
exactly this) is a required runtime dependency (`backend/pyproject.toml`), not just a
dev/test one — omitting it in a deployment image will raise `ZoneInfoNotFoundError` the
first time any IST helper runs.

## What was NOT touched

- No attendance/timesheet feature exists anywhere in this codebase (confirmed by
  repo-wide grep) — there was nothing to migrate.
- No existing MongoDB timestamps were rewritten/migrated. `tz_aware=True` changes how a
  stored value is *decoded into Python*, not what's stored on disk — completely
  backward-compatible with every document already in the database.
- API response wire format: still ISO 8601 strings, just now carrying an explicit UTC
  offset (`+00:00`) instead of none — every correct ISO-8601 consumer handles this
  transparently; only a consumer that was silently assuming "naive means UTC" (as this
  app's own frontend, pre-fix, incorrectly did) would need updating, which this work did.
