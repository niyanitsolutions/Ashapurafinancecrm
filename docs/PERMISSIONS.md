# Permissions / Access Control

Module 3 — **approved and frozen** once its completion checklist is signed off. Implemented in `backend/app/features/access_control/`. Values (which roles have which permissions) are entirely DB-driven, per the project's core rule — this document describes the model and how to consume it; the actual catalogue is data, created via the API/UI, not code.

## Model

```
Role                — a named collection of grants (e.g. "Branch Manager"). name unique, status active/inactive.

Permission          — catalog entry: {module, resource, actions[]}. Describes what's
                       POSSIBLE for a (module, resource) pair — not a grant. module/resource
                       are free text by design (data-driven — adding a future module means
                       creating new Permission records, never touching this engine's code).

RolePermission       — the actual grant: {role_id, permission_id, granted_actions[],
                       department_ids?, branch_ids?}. granted_actions must be a subset of
                       the referenced Permission's actions. department_ids/branch_ids
                       (null = unrestricted) scope the grant to specific
                       departments/branches (Module 2's collections, read-only reference).

EmployeeRole         — {employee_id, role_id}. Many-to-many — an employee can hold
                       multiple roles simultaneously.

TemporaryAccess      — time-bound extra grants: {employee_id, grants[{permission_id,
                       actions[]}], start_date, end_date, start_time, end_time, reason,
                       status}. See Time Windows below.

GeoException         — {employee_id, geo_fence_id?, allowed_location{lat,lng},
                       radius_meters, start_date, end_date, start_time, end_time, reason,
                       status}. Enforced (Module 10) for Lead Creation and Document
                       Collection — see docs/GEO_FENCING.md.
```

`app/constants/permissions.py:permission_key` (Foundation) is a `"<feature>:<action>"` 2-part helper and is **not used** by this module — Module 3 needs a 3-part (module, resource, action) shape instead, and Foundation's file is frozen. No file under `app/features/{auth,employee}/` or `app/constants/` was touched to build this.

## Fixed Action Vocabulary

Unlike module/resource, `PermissionAction` (`backend/app/features/access_control/constants.py`) **is** a fixed, closed set — given as such in the brief: `view, create, edit, delete, assign, approve, reject, export, import, upload, download, print, share`. A `RolePermission.granted_actions` entry must be within both this set and the referenced `Permission.actions`.

## Time Windows (Temporary Access / Geo Exception)

`start_date`/`end_date` + `start_time`/`end_time` (4 separate fields, not 2 datetimes) are read as a **daily recurring window** — e.g. "accessible 9am–5pm, each day, from Jan 1 to Jan 15" — not one continuous span. This is an interpretation of an ambiguous brief, not a confirmed requirement; flagged in `docs/KNOWN_LIMITATIONS.md`. Overnight windows (e.g. 22:00–06:00) are not supported — string comparison of `"HH:MM"` only works for same-day ranges.

**Expiry is lazy** — evaluated at permission-check time (`PermissionEngine._within_daily_window`), not via a background sweep job. A grant outside its window is simply never valid; there's no separate "expired" status stored, only `active`/`revoked`. This is correct and sufficient for access control; a sweep job (for reporting/audit visibility) would belong to the future Reminder & Notification Engine module, not here.

## Enforcement — `PermissionEngine`

`backend/app/features/access_control/permission_engine.py`:

```python
async def has_permission(user, *, module, resource, action, department_id=None, branch_id=None) -> bool
```

Resolution order: **Owner always passes** (superuser bypass, matching the rest of the system) → Customer/Referral Partner always fail (this system is staff-only) → resolve the caller's `Employee` record → check role grants (with department/branch scope) → check active `TemporaryAccess` grants within their daily window → otherwise deny.

`require_permission(module, resource, action)` is a FastAPI dependency factory:

```python
current_user: Annotated[User, require_permission("loan_management", "leads", "view")]
```

**This is new infrastructure — Module 2's existing endpoints are deliberately not retrofitted to use it**, per the Module 2 freeze. Module 2 keeps its simple Owner-vs-self check unchanged.

**Module 4 (Settings/Master Data) is the first real consumer** — every endpoint under `backend/app/features/system_settings/router.py` is gated with `require_permission("system_settings", resource, action)` (`resource` is e.g. `lead_sources`, `loan_products`, `api_settings`, ...; `action` is `view`/`create`/`edit`). `scripts/seed.py` seeds a matching catalog entry for every Settings resource so an Owner can grant them to a role immediately, without first having to hand-create the catalog row via `POST /permissions`. Owner bypasses the engine entirely either way, so this only matters once an Owner delegates a Settings resource to an Employee role.

## Frontend

The Sidebar (`frontend/src/components/layout/Sidebar.tsx`) still renders a static nav list — filtering it by `PermissionEngine.get_accessible_modules` is deferred to the Dashboard Framework module, which is where the sidebar itself gets built out. This module ships the pages listed in `docs/architecture/MODULES.md` (Role List/Details, Permission Matrix, Assign Role, Temporary Access, Geo Exception) as standalone routes, same pattern as Module 2.
