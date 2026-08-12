# UI/UX

## Design Language

Modern fintech: dark sidebar, light content area, white cards, orange accent.

## Theme Tokens

Defined in `frontend/src/theme/` — one file per concern, all consumed by `tailwind.config.ts`:

| Token file | Contents |
|---|---|
| `colors.ts` | sidebar `#121212`, primary `#FF7A00`, primary-light `#FF9A3D`, background `#F5F7FA`, card white, border `#E5E7EB`, text `#111827`, success/warning/danger |
| `spacing.ts` | layout constants (sidebar width, topbar height) |
| `typography.ts` | font family, font sizes |
| `icons.ts` | reserved — icon library not chosen yet |
| `radius.ts` | border radius scale, including a `card` token |
| `shadow.ts` | `card` and `dropdown` shadow presets |
| `animation.ts` | transition duration scale |

Backend mirrors the color values in `backend/app/constants/colors.py` for cases where the API needs to hint a display color (e.g. status badge color) — kept in sync manually until a shared design-token pipeline exists.

## Layout

`frontend/src/components/layout/`: `Sidebar` (fixed, dark, nav driven by the DB-backed `nav_items` catalog filtered through `PermissionEngine` — implemented in Module 5, see `docs/decisions/DECISIONS.md` #033), `Topbar` (light; Quick Search, Notification Bell, Profile Menu — the latter two live in `features/dashboard/components/` since they need Dashboard's API, not generic enough for this shared folder), `AppShell` (composes both + `<Outlet/>`, wraps every authenticated route as of Module 5 — previously a Foundation-era placeholder no route actually rendered inside). Content area: white cards on a light gray background, per the fintech design language.

Icon usage today is plain emoji glyphs (🔔, ☰) inline in the few places icons appear — `theme/icons.ts` remains reserved/unchosen (see `docs/KNOWN_LIMITATIONS.md`); a real icon library is still a future decision, not forced by Module 5.

**Standalone pages** (not behind the sidebar shell — auth screens, and anything else that renders before/outside a logged-in session) use `AuthPageLayout` (`frontend/src/features/auth/components/AuthPageLayout.tsx`): centered card, light background, same theme tokens. Reused as the pattern for any future pre-auth or full-screen page rather than each one rebuilding the same centered-card wrapper.

**Pages behind the shell** (everything under `RequireAuth`, i.e. all of Modules 2–4's screens) still use `SimplePageLayout` for their own title/back-link header, now nested inside `AppShell`'s Topbar — a minor, accepted visual redundancy (two header rows stacked) rather than editing those modules' frozen page components; see `docs/KNOWN_LIMITATIONS.md`.

## Component Inventory (folders, filled in per-feature as built)

`components/{cards, forms, tables, charts, dialogs, timeline, uploads, navigation}` — shared, feature-agnostic UI. Feature-specific UI lives inside that feature's own `features/<name>/` folder, not here.

## Responsiveness

Desktop and tablet targets for Phase 1; layout uses relative units and flex/grid so it degrades reasonably on mobile web ahead of the native Flutter apps, but mobile web is not a design target in its own right. `AppShell`'s `Sidebar` is implemented responsively (Module 5): fixed and always visible at the `lg` breakpoint and above, an off-canvas drawer (hamburger-toggled from `Topbar`) below it.
