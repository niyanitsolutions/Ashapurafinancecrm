// Browser evidence against real components and synthetic intercepted API responses.
// Does not contact CRM services or certify database acceptance.
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs";

const origin = "http://127.0.0.1:5187";
const output = resolve("docs/screenshots/attendance-calendar-2026-10-26");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const evidence = [];
const envelope = data => ({ success: true, data, error: null, meta: null });
const statuses = ["FOLLOW UP PENDING", "NEXT FOLLOW UP", "DISBURSE", "REJECTED WITH REASON"];
const contrast = (foreground, background) => {
  const luminance = color => color.match(/[\d.]+/g).slice(0, 3).map(Number).map(channel => channel / 255).reduce((sum, channel, index) => sum + [0.2126, 0.7152, 0.0722][index] * (channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4), 0);
  const a = luminance(foreground), b = luminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
};
const rgb = ["rgb(252, 165, 165)", "rgb(147, 197, 253)", "rgb(134, 239, 172)", "rgb(253, 224, 71)"];
const areas = ["follow-ups", "progress", "sessions", "issues"];
try {
  for (const role of ["owner", "employee"]) for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1050 }, timezoneId: "America/Los_Angeles", reducedMotion: "reduce" });
    await context.addInitScript(() => localStorage.setItem("afs_refresh_token", "synthetic-calendar-only"));
    const queries = [], errors = [];
    const followups = statuses.map((status, index) => ({ id: `synthetic-${index}`, date: "2026-10-26", customer_name: `Synthetic Customer ${index}`, customer_number: "9000000000", status, employee_name: "Synthetic Employee", due_date: "2026-10-27" }));
    await context.route("**/*", async route => {
      const request = route.request(), url = new URL(request.url());
      if (!url.pathname.startsWith("/api/v1/")) return url.origin === origin ? route.continue() : route.abort();
      const path = url.pathname.slice("/api/v1".length);
      let data = [];
      if (path === "/auth/refresh") data = { access_token: "synthetic-calendar-only", refresh_token: "synthetic-calendar-only" };
      else if (path === "/auth/profile") data = { user_id: "aaaaaaaaaaaaaaaaaaaaaaaa", role, name: "Synthetic Employee", mobile: "", must_change_password: false };
      else if (path === "/my-permissions") data = { grants: role === "owner" ? {} : Object.fromEntries(areas.map(area => [`daily_operations:${area}`, ["view", "export"]])) };
      else if (path === "/dashboard/nav") data = ["dashboard", "daily_follow-ups", "daily_progress", "daily_sessions", "daily_issues"].map((key, order) => ({ key, label: key, route: "/", order }));
      else if (path.includes("unread-count")) data = { count: 0 };
      else if (path === "/daily-operations/lookups") data = { self_id: "aaaaaaaaaaaaaaaaaaaaaaaa", employees: [{ id: "bbbbbbbbbbbbbbbbbbbbbbbb", name: "Synthetic Employee" }], leads: [], cases: [] };
      else if (path === "/daily-operations/follow-ups") data = { items: followups, total: 4 };
      else if (path.startsWith("/daily-operations/sessions")) {
        const month = url.searchParams.get("month") ?? "2026-10";
        queries.push({ path, params: Object.fromEntries(url.searchParams) });
        if (path.endsWith("/export")) return route.fulfill({ contentType: "text/csv", body: `DATE,EMPLOYEE NAME\n${month}-27,Synthetic Employee\n` });
        const date = `${month}-27`;
        data = { month, business_timezone: "Asia/Kolkata", total: 1, items: [{ id: `synthetic:${date}`, date, employee_name: "Synthetic Employee", login_at: `${date}T00:00:00+05:30`, logout_at: `${date}T00:30:00+05:30`, status: "logged_out", recorded_seconds: 1800, sessions: [{ id: "synthetic-family", login_at: `${month}-26T23:30:00+05:30`, logout_at: `${date}T00:30:00+05:30`, segment_start_at: `${date}T00:00:00+05:30`, segment_end_at: `${date}T00:30:00+05:30`, segment_status: "finalized", status: "logged_out", end_reason: "manual_logout", recorded_seconds: 1800 }] }] };
      }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(envelope(data)) });
    });
    const page = await context.newPage();
    page.on("pageerror", error => errors.push(error.message));
    await page.clock.install();
    await page.goto(`${origin}/daily-operations/follow-ups`, { waitUntil: "networkidle" });
    await page.getByText("Synthetic Customer 0", { exact: true }).waitFor();
    assert.equal(await page.getByRole("navigation", { name: "Daily Update tabs" }).getByRole("link").count(), 5);
    for (let index = 0; index < 4; index++) {
      const row = page.getByRole("row").filter({ hasText: `Synthetic Customer ${index}` });
      await page.mouse.move(0, 0);
      const colors = await row.locator("td").evaluateAll(cells => cells.map(cell => getComputedStyle(cell).backgroundColor));
      assert(colors.every(color => color === rgb[index]), `${role}/${width}/${statuses[index]}: ${colors}`);
      assert(await row.getByText(statuses[index], { exact: true }).isVisible());
      const textColor = await row.locator("td").first().evaluate(cell => getComputedStyle(cell).color);
      assert(contrast(textColor, rgb[index]) >= 4.5);
      for (const button of await row.getByRole("button").all()) {
        const style = await button.evaluate(element => ({ foreground: getComputedStyle(element).color, background: getComputedStyle(element).backgroundColor }));
        assert(contrast(style.foreground, style.background === "rgba(0, 0, 0, 0)" ? rgb[index] : style.background) >= 4.5, JSON.stringify(style));
      }
    }
    const first = page.getByRole("row").filter({ hasText: "Synthetic Customer 0" });
    await first.getByRole("button").first().focus();
    assert(await first.evaluate(row => row.contains(document.activeElement)));
    await page.waitForFunction(() => getComputedStyle(document.querySelector("tbody tr td")).backgroundColor === "rgb(248, 113, 113)");
    await page.keyboard.press("Tab");
    assert(await page.locator("tbody").evaluate(body => body.contains(document.activeElement)));
    await page.getByRole("heading", { name: "Daily Follow-up Data", exact: true }).click();
    await page.mouse.move(0, 0);
    await page.screenshot({ path: resolve(output, `${role}-${width}-colors.png`), fullPage: true });
    followups[0].status = "NEXT FOLLOW UP";
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => document.querySelector("tbody tr")?.textContent.includes("NEXT FOLLOW UP"));
    await page.goto(`${origin}/daily-operations/sessions`, { waitUntil: "networkidle" });
    await page.getByLabel("Month", { exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelector('input[type="month"]')?.value === "2026-10");
    assert(await page.getByLabel("Employee name", { exact: true }).isVisible());
    assert(await page.locator("summary").filter({ hasText: /^More filters$/ }).isVisible());
    const attendance = page.locator("tbody tr").first();
    assert(!/26(?: Oct|\/10)/.test(await attendance.innerText()), "Summary must not display yesterday's login");
    assert((await attendance.innerText()).includes("12:00"));
    await attendance.getByRole("button", { name: "Session history", exact: true }).click();
    const dialog = page.getByRole("dialog");
    assert(await dialog.getByText(/Daily segment:/).isVisible());
    assert((await dialog.getByText(/Actual login:/).innerText()).includes("26/10/2026"));
    assert.equal(await dialog.getByRole("button", { name: "Correct session", exact: true }).count(), role === "owner" ? 1 : 0);
    await page.keyboard.press("Escape");
    await page.getByLabel("Employee name", { exact: true }).fill("Synthetic");
    await page.waitForURL(/employee_name=Synthetic/);
    await page.getByLabel("Month", { exact: true }).fill("2026-09");
    await page.waitForURL(/month=2026-09/);
    assert.equal(new URL(page.url()).searchParams.get("employee_name"), "Synthetic", page.url());
    await page.reload({ waitUntil: "networkidle" });
    assert.equal(await page.getByLabel("Month", { exact: true }).inputValue(), "2026-09");
    await page.locator("summary").filter({ hasText: /^Export$/ }).click();
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "CSV", exact: true }).click();
    const download = await downloadPromise;
    const file = resolve(output, `${role}-${width}-september.csv`);
    await download.saveAs(file);
    assert((await readFile(file, "utf8")).includes("2026-09-27"));
    assert(queries.some(query => query.path.endsWith("/export") && query.params.month === "2026-09" && query.params.employee_name === "Synthetic"));
    await page.locator("summary").filter({ hasText: /^Export$/ }).click();
    await page.screenshot({ path: resolve(output, `${role}-${width}-month.png`), fullPage: true });
    const overflow = await page.evaluate(() => ({ pageWidth: document.documentElement.scrollWidth, viewport: innerWidth, tableWidth: document.querySelector("table")?.scrollWidth }));
    assert(overflow.pageWidth <= width + 1, JSON.stringify(overflow));
    assert.deepEqual(errors, []);
    evidence.push({ role, width, result: "PASS", checks: ["four cell colors", "text and action contrast >= 4.5", "keyboard focus", "status poll update", "day segment history", "server month default", "URL reload", "employee filter", "filtered export", "responsive page"], overflow });
    await context.close();
  }
} finally {
  await browser.close();
  await writeFile(resolve(output, "results.json"), JSON.stringify({ kind: "synthetic-api-browser-evidence", evidence }, null, 2));
}
console.log(JSON.stringify(evidence));
