# Geo Fencing (Module 10)

Stage 1 of a larger, explicitly user-requested addition (Geo Fencing / Temporary
Permissions / MSG91 / Bulk Messaging), delivered in stages with a check-in between each.
This document covers Stage 1 only — GeoFence CRUD and real enforcement.

## Scope

Two capabilities the spec asked for already existed, fully built, before this module —
see `docs/PERMISSIONS.md` and `docs/decisions/DECISIONS.md` #109:

- **Temporary Permissions** — Access Control's `TemporaryAccess` (Module 3), enforced
  live inside `PermissionEngine`. Unmodified by this module.
- **Geo Fencing Exceptions** — Access Control's `GeoException` (Module 3), Owner-only,
  audited. Extended (decision 110) with an optional `geo_fence_id` reference to a named
  `GeoFence`; otherwise unmodified.

What this module actually adds:

1. **`GeoFence`** — a named work-area (`backend/app/features/geo_fencing/`): Area Name,
   Address, Latitude, Longitude, Radius (meters), Allowed Activities, Status
   (active/inactive). Owner (or a granted role) can create/view/edit/activate/deactivate/
   search/filter/paginate, and delete only when no *active* `GeoException` references it.
2. **Real enforcement** (`enforcement.py`) — the piece that previously didn't exist
   anywhere in this codebase.

## Model

```
GeoFence          — {area_name, address, latitude, longitude, radius_meters,
                     allowed_activities[], status}. Delete blocked while an active
                     GeoException references it (deactivate instead).

GeoException       — (Module 3, extended) {employee_id, geo_fence_id?, allowed_location
                     {lat,lng}, radius_meters, start_date, end_date, start_time, end_time,
                     reason, status}. geo_fence_id is provenance only — the exception's own
                     allowed_location/radius_meters are its source of truth, prefilled from
                     the fence at creation time but independent of it afterward.
```

`GeoActivity` (fixed vocabulary): `lead_creation`, `document_collection`, `customer_visit`,
`loan_application`, `insurance_application`. All 5 are valid `allowed_activities` values;
only the first two are ever actually enforced — see "Enforcement scope" below.

## Enforcement — `enforce_geo_fence`

`backend/app/features/geo_fencing/enforcement.py`:

```python
async def enforce_geo_fence(db, *, actor: User, activity: str, latitude: float | None, longitude: float | None) -> None
```

Resolution order:

1. Owner bypasses entirely (superuser, matching every other engine in this codebase).
2. If zero active `GeoFence`s list `activity` → no-op. Geo-fencing is opt-in per activity;
   an activity with nothing configured behaves exactly as before this module existed.
3. If fences are configured but no coordinates were supplied → reject
   (`"Location is required for this action."`). Never silently allow.
4. Any of the employee's currently-valid `GeoException`s (same daily-recurring-window
   evaluation `PermissionEngine` uses for Temporary Access, via the shared
   `app/utils/datetime.py:within_daily_window`) bypasses the distance check entirely.
5. Otherwise, haversine distance (stdlib `math`, `geomath.py`) against every candidate
   fence; inside **any** matching fence's radius → allow. Outside all of them → reject
   (`"You're outside the permitted work area for this action."`).
6. Every outcome (allowed or denied) writes one audit log entry (`write_audit_log`) —
   activity, employee, which fence/exception matched — never raw coordinates.

## Enforcement scope

Only two activities are wired to a real endpoint:

| Activity | Endpoint |
|---|---|
| `lead_creation` | `POST /leads` (`leads/router.py:create_lead`) |
| `document_collection` | `POST /{case_id}/documents/verify` (both `loan_management` and `insurance_management`) |

`customer_visit`, `loan_application`, `insurance_application` have no real,
single, employee-initiated action anywhere in this codebase to attach enforcement to —
see decision 111 in `docs/decisions/DECISIONS.md` for why, and
`docs/KNOWN_LIMITATIONS.md`'s Module 10 section. They remain selectable on a `GeoFence`
(for completeness / possible future use) but have zero runtime effect.

Each of the 3 wired endpoints gained exactly one optional `latitude`/`longitude` field and
one `enforce_geo_fence(...)` call immediately before its existing service call — nothing
else in those (frozen) router functions changed. A caller that never sends coordinates
behaves byte-for-byte as before.

## Frontend

- **Settings → Geo Fencing** (`/settings/geo-fencing`) — new page, list/create/edit/
  activate/deactivate/delete/search/filter/paginate.
- **Administration → Geo Exceptions** (`/geo-exceptions`, pre-existing) — gained a "Geo
  Fence" dropdown that prefills latitude/longitude/radius, still overridable.
- **Create Lead** and **Verify Documents** (Loan/Insurance case detail) — best-effort
  `navigator.geolocation` capture (`frontend/src/shared/geolocation.ts`) before submitting;
  permission-denied/unavailable/timeout all resolve to no coordinates, never blocking the
  form. The backend is authoritative either way.

## Permissions

One resource: `geo_fencing:fences` (view/create/edit/delete), gated by the same
`require_permission` engine every module since Module 4 uses. Owner bypasses it.

## Known limitations

See `docs/KNOWN_LIMITATIONS.md`'s Module 10 section for the full list (unenforced
activities, no live GPS/browser testing, overlap-is-a-warning-not-a-block, etc.).
