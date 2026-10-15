# CRM visual review — 15 October 2026

Evidence uses actual local frontend routes with explicitly synthetic API fixtures,
temporary headless Chrome contexts and approved local Playwright. No customer data,
real backend session or provider was used. Four screens at 1440/390px were checked;
this is not visual acceptance of every CRM page. All 164 route/layout/redirect
entries are inventoried separately in [CRM_ROUTE_INVENTORY.md](CRM_ROUTE_INVENTORY.md).

1. Shared orange gradients, heavy shadows and large content typography reduced
   density. Content now uses the requested orange/charcoal/white tokens, quiet
   borders, solid accessible primary actions and responsive spacing. Compare
   [campaign before](screenshots/voice-upgrade/before/campaigns-1440.png) with
   [campaign after](screenshots/voice-upgrade/after/campaigns-1440.png).
2. Narrow content could push cards or empty table content outside readable bounds.
   Cards can now shrink, titles wrap, and empty states remain readable within the
   viewport. Inspect [mobile leads](screenshots/voice-upgrade/after/leads-390.png).
   Wide business tables retain horizontal scrolling; columns were not removed.
3. Shared fields lacked consistent label/error associations. Input, select and
   textarea now provide stable IDs, invalid state and help/error references while
   preserving caller-provided values. Three automated accessibility association
   tests passed; this does not constitute a complete assistive-technology audit.
4. Native connection administration now distinguishes configuration, read-only
   probe evidence and live blockers, with write-only credential replacement.
   Inspect [desktop](screenshots/voice-upgrade/after/native-connections-1440.png)
   and [mobile](screenshots/voice-upgrade/after/native-connections-390.png).
5. Sidebar preservation was a strict requirement. Sidebar/navigation files and
   route guards were not changed. All six comparable sidebar metadata captures
   match; all three desktop sidebar crops match pixel-for-pixel, including original
   colors, widths and shadows. See [comparison evidence](screenshots/voice-upgrade/sidebar-comparison.json).

[Latest capture evidence](screenshots/voice-upgrade/after/evidence.json): eight
captures, no page errors or document-level horizontal overflow. Mobile headings
and empty states were visually inspected. Shared design primitives affect their
consuming pages across the inventory; bespoke review of the remaining CRM flows,
populated/long financial tables, validation/loading/error states, keyboard and
screen-reader journeys remains outstanding. No claim of a complete whole-CRM
redesign or production browser acceptance is made.
