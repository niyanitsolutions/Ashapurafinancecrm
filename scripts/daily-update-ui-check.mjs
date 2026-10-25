// Local browser regression checks against real components and isolated synthetic API
// fixtures. This is navigation/layout evidence, not real-database acceptance evidence.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs";

const origin = "http://127.0.0.1:5175";
const output = resolve("docs/screenshots/daily-update-2026-10-25");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const evidence = [];
const areaNames = ["Daily Follow-up Data", "Loan Progress Tracking", "Employee Login & Logout", "Inquiry or Issue", "Import & Export Centre"];
const paths = ["follow-ups", "progress", "sessions", "issues", "transfers"];
const envelope = data => ({ success: true, data, error: null, meta: null });

async function fixtureContext(role, width) {
  const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: "reduce" });
  const requests = [];
  await context.addInitScript(() => localStorage.setItem("afs_refresh_token", "synthetic-navigation-test-only"));
  await context.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/v1/")) return url.origin === origin ? route.continue() : route.abort();
    const path = url.pathname.slice("/api/v1".length);
    let data = [];
    if (path === "/auth/refresh") data = { access_token: "synthetic-navigation-access-only", refresh_token: "synthetic-navigation-test-only" };
    else if (path === "/auth/profile") data = { user_id: "aaaaaaaaaaaaaaaaaaaaaaaa", role, mobile: "", name: `Synthetic ${role}`, must_change_password: false };
    else if (path === "/my-permissions") data = { grants: role === "employee" ? { "daily_operations:issues": ["view"] } : {} };
    else if (path === "/dashboard/nav") {
      const keys = role === "owner"
        ? ["dashboard", "leads", "loan_cases", "insurance_cases", "daily_follow-ups", "daily_progress", "daily_sessions", "daily_issues"]
        : ["daily_issues"];
      data = keys.map((key, order) => ({ key, label: key, route: "/", order }));
    } else if (path.includes("unread-count")) data = { count: 0 };
    else if (path.startsWith("/daily-operations/")) {
      requests.push(path);
      data = { items: [], total: 0, statuses: {} };
    }
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(envelope(data)) });
  });
  return { context, requests };
}

try {
  for (const width of [1440, 390]) {
    const { context, requests } = await fixtureContext("owner", width);
    const page = await context.newPage();
    const errors = []; page.on("pageerror", error => errors.push(error.message));
    await page.goto(`${origin}/daily-operations`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.getByRole("heading", { name: "Daily Follow-up Data", exact: true }).waitFor();
    const bar = page.getByRole("navigation", { name: "Daily Update tabs" });
    assert.equal(await bar.getByRole("link").count(), 5);
    assert.equal(await page.locator("aside").getByRole("link", { name: "Daily Update", exact: true }).count(), 1);
    assert.equal(await page.locator("aside").getByRole("link", { name: "Daily Follow-up Data", exact: true }).count(), 0);
    assert.equal(await page.evaluate(() => document.querySelector("aside").contains(document.querySelector('[aria-label="Daily Update tabs"]'))), false);
    await page.evaluate(() => { window.__dailyUpdateSameDocument = true; });
    for (let index = 0; index < paths.length; index++) {
      const tab = bar.getByRole("link", { name: areaNames[index], exact: true });
      await tab.click();
      await page.getByRole("heading", { name: areaNames[index], exact: true }).waitFor();
      assert.equal(await tab.getAttribute("aria-current"), "page");
      assert.match(await tab.getAttribute("class"), /border-primary/);
      assert.equal(new URL(page.url()).pathname, `/daily-operations/${paths[index]}`);
      assert.equal(await page.evaluate(() => window.__dailyUpdateSameDocument), true);
    }
    const overflow = await bar.evaluate(element => ({ scroll: element.scrollWidth, width: element.clientWidth, mode: getComputedStyle(element).overflowX }));
    assert.equal(overflow.mode, "auto");
    if (width === 390) assert.ok(overflow.scroll > overflow.width);
    await page.goto(`${origin}/daily-operations/issues?search=Internal&status=OPEN&page=2`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.getByRole("heading", { name: "Inquiry or Issue", exact: true }).waitFor();
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await page.getByRole("heading", { name: "Inquiry or Issue", exact: true }).waitFor();
    assert.equal(await page.getByLabel("Search", { exact: true }).inputValue(), "Internal");
    assert.ok(requests.filter(path => path === "/daily-operations/issues").length > 0);
    // Keyboard-activate the single sidebar link; mobile drawer uses the existing menu.
    if (width === 390) await page.getByRole("button", { name: "Open menu", exact: true }).click();
    const sidebarLink = page.locator("aside").getByRole("link", { name: "Daily Update", exact: true });
    assert.match(await sidebarLink.getAttribute("class"), /bg-primary/);
    await sidebarLink.focus(); await page.keyboard.press("Enter");
    await page.getByRole("heading", { name: "Daily Follow-up Data", exact: true }).waitFor();
    await page.screenshot({ path: resolve(output, `owner-${width}.png`), fullPage: true });
    assert.deepEqual(errors, []);
    evidence.push({ role: "owner", width, tabs: 5, activeStyles: "PASS", refreshAndQuery: "PASS", keyboardAndSidebar: "PASS", overflow, pageErrors: errors });
    await context.close();
  }
  const { context, requests } = await fixtureContext("employee", 1440);
  const page = await context.newPage();
  await page.goto(`${origin}/daily-operations`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.getByRole("heading", { name: "Inquiry or Issue", exact: true }).waitFor();
  assert.equal(await page.getByRole("navigation", { name: "Daily Update tabs" }).getByRole("link").count(), 1);
  await page.goto(`${origin}/daily-operations/progress`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.getByRole("alert").filter({ hasText: "do not have permission" }).waitFor();
  assert.equal(requests.includes("/daily-operations/progress"), false);
  await page.screenshot({ path: resolve(output, "employee-denied.png"), fullPage: true });
  evidence.push({ role: "employee", permittedTabs: ["issues"], unauthorizedProgressMount: "BLOCKED", unauthorizedProgressRequests: 0 });
  await context.close();
  await writeFile(resolve(output, "evidence.json"), JSON.stringify({ fixtures: "Synthetic local API responses; no production data or persistence verification", checks: evidence }, null, 2));
  console.log(JSON.stringify({ status: "PASS", scenarios: evidence.length, output }));
} finally {
  await browser.close();
}
