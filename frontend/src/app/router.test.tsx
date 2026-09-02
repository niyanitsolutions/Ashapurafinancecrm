import { describe, expect, it } from "vitest";
import { router } from "./router";

// Locks in the Loan/Insurance Management tab-navigation fix directly against the real
// route config (not just the pattern proven in CaseListPage.test.tsx): every sibling
// tab under /loan-management and /insurance-management renders the same shared
// <CaseListPage>-backed component at the same <Outlet/> position, so each one needs its
// own distinct `key` or React Router will reuse the instance and carry over stale
// filter state from whichever tab was opened first (the real production bug — see
// CaseListPage.test.tsx's "tab-to-tab navigation" describe block for the full story).

interface RouteLike {
  path?: string;
  element?: unknown;
  children?: RouteLike[];
}

// The real router nests /loan-management and /insurance-management several layout
// levels deep (RequireAuth > AppShell > ...) — recursing avoids hardcoding that depth,
// so this test doesn't break every time an unrelated layout route is added above them.
function findRouteByPath(routes: RouteLike[], path: string): RouteLike | undefined {
  for (const route of routes) {
    if (route.path === path) return route;
    if (route.children) {
      const found = findRouteByPath(route.children, path);
      if (found) return found;
    }
  }
  return undefined;
}

function findRoute(children: RouteLike[] | undefined, path: string): RouteLike | undefined {
  return children?.find((r) => r.path === path);
}

describe("router — Loan/Insurance Management tab routes stay keyed", () => {
  it("every /loan-management tab route's element has a distinct, non-empty key", () => {
    const loanManagement = findRouteByPath(router.routes as RouteLike[], "/loan-management");
    expect(loanManagement).toBeTruthy();
    const tabPaths = [
      "cases", "credit-evaluation", "offer-acceptance", "additional-documents", "rv-ov-ref",
      "esign-nach-kyc", "final-evaluation", "send-for-disbursement", "disbursements", "on-hold", "rejected",
    ];
    const keys = tabPaths.map((path) => {
      const route = findRoute(loanManagement?.children, path);
      expect(route, `route for path "${path}" should exist`).toBeTruthy();
      const key = (route?.element as { key?: string | null })?.key;
      expect(key, `tab route "${path}" must have a distinct key to force a remount on tab switch`).toBeTruthy();
      return key;
    });
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("Top Up Loan: lives under /leads, not /loan-management (moved per production spec)", () => {
    const leads = findRouteByPath(router.routes as RouteLike[], "/leads");
    expect(leads).toBeTruthy();
    expect(findRoute(leads?.children, "top-up")).toBeTruthy();

    const loanManagement = findRouteByPath(router.routes as RouteLike[], "/loan-management");
    expect(loanManagement).toBeTruthy();
    expect(findRoute(loanManagement?.children, "top-up")).toBeUndefined();
  });

  it("Re-Eligible: moved to /leads/re-eligible; old /loan-management/re-eligible redirects", () => {
    const leads = findRouteByPath(router.routes as RouteLike[], "/leads");
    expect(findRoute(leads?.children, "re-eligible")).toBeTruthy();

    const loanManagement = findRouteByPath(router.routes as RouteLike[], "/loan-management");
    expect(findRoute(loanManagement?.children, "re-eligible")).toBeUndefined();

    // Old URL still resolves — to a redirect element, not a dead layout outlet.
    const redirect = findRouteByPath(router.routes as RouteLike[], "/loan-management/re-eligible");
    expect(redirect?.element).toBeTruthy();
  });

  it("every /insurance-management tab route's element has a distinct, non-empty key", () => {
    const insuranceManagement = findRouteByPath(router.routes as RouteLike[], "/insurance-management");
    expect(insuranceManagement).toBeTruthy();
    const tabPaths = ["cases", "policies-issued", "re-eligible", "rejected"];
    const keys = tabPaths.map((path) => {
      const route = findRoute(insuranceManagement?.children, path);
      expect(route, `route for path "${path}" should exist`).toBeTruthy();
      const key = (route?.element as { key?: string | null })?.key;
      expect(key, `tab route "${path}" must have a distinct key to force a remount on tab switch`).toBeTruthy();
      return key;
    });
    expect(new Set(keys).size).toBe(keys.length);
  });
});
