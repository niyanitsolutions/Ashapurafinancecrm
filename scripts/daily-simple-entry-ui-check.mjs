// Real UI interaction with isolated synthetic API fixtures. No production data/network.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs";

const origin = "http://127.0.0.1:5175";
const output = resolve("docs/screenshots/daily-simple-entry-2026-10-25");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const evidence = [];
const employeeId = "bbbbbbbbbbbbbbbbbbbbbbbb";
const ownerId = "aaaaaaaaaaaaaaaaaaaaaaaa";
const envelope = data => ({ success: true, data, error: null, meta: null });
const names = ["Daily Follow-up Data", "Loan Progress Tracking", "Employee Login & Logout", "Inquiry or Issue", "Import & Export Centre"];

try {
  for (const role of ["owner", "employee"]) for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1050 }, reducedMotion: "reduce" });
    await context.addInitScript(() => localStorage.setItem("afs_refresh_token", "synthetic-simple-entry-only"));
    const rows = { "follow-ups": [], progress: [], issues: [], sessions: [{ id: "synthetic-session-family", date: "2026-10-25", employee_name: "Synthetic Employee", login_at: "2026-10-25T04:00:00Z", logout_at: null, status: "active", recorded_seconds: null }] };
    const writes = [];
    let sequence = 1;
    await context.route("**/*", async route => {
      const request = route.request(); const url = new URL(request.url());
      if (!url.pathname.startsWith("/api/v1/")) return url.origin === origin ? route.continue() : route.abort();
      const path = url.pathname.slice("/api/v1".length); const method = request.method();
      let data = [];
      if (path === "/auth/refresh") data = { access_token: "synthetic-simple-entry-only", refresh_token: "synthetic-simple-entry-only" };
      else if (path === "/auth/profile") data = { user_id: role === "owner" ? ownerId : employeeId, role, name: `Synthetic ${role}`, mobile: "", must_change_password: false };
      else if (path === "/my-permissions") data = { grants: role === "owner" ? {} : Object.fromEntries(Object.keys(rows).map(area => [`daily_operations:${area}`, area === "sessions" ? ["view", "export"] : ["view", "create", "edit", "export", "import", ...(area === "issues" ? ["approve"] : [])]])) };
      else if (path === "/dashboard/nav") data = ["dashboard", "leads", "loan_cases", "insurance_cases", "daily_follow-ups", "daily_progress", "daily_sessions", "daily_issues", ...(role === "owner" ? ["invoices", "voice_assistant", "referral_partners", "reports", "messaging", "support_tickets", "integrations"] : [])].map((key, order) => ({ key, label: key, route: "/", order }));
      else if (path === "/daily-operations/lookups") data = { self_id: role === "owner" ? ownerId : employeeId, self_name: `Synthetic ${role}`, employees: [{ id: employeeId, name: "Synthetic Employee" }], leads: [], cases: [] };
      else if (path.includes("unread-count")) data = { count: 0 };
      else if (path.startsWith("/daily-operations/")) {
        const [, , area, id] = path.split("/");
        if (!(area in rows)) return route.fulfill({ contentType: "application/json", body: JSON.stringify(envelope([])) });
        if (method === "GET" && !id) data = { items: rows[area], total: rows[area].length, statuses: {} };
        else if (method === "GET") data = rows[area].find(row => row.id === id);
        else if (method === "POST") {
          const body = request.postDataJSON();
          data = { ...body, id: String(sequence++).padStart(24, "0"), version: 1, source: "manual", assigned_to: body.assigned_to ?? (role === "owner" ? ownerId : employeeId), history: [] };
          rows[area].push(data); writes.push({ method, area });
        } else if (method === "PATCH") {
          const body = request.postDataJSON(); const row = rows[area].find(row => row.id === id);
          assert.equal(body.version, row.version);
          Object.assign(row, body, { version: row.version + 1 }); data = row; writes.push({ method, area });
        } else if (method === "DELETE") {
          assert.equal(role, "owner", "Employees must never issue a delete request.");
          rows[area] = rows[area].filter(row => row.id !== id); data = { deleted: true }; writes.push({ method, area });
        }
      }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(envelope(data)) });
    });
    const page = await context.newPage(); const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(`${origin}/daily-operations`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.getByRole("heading", { name: names[0], exact: true }).waitFor();
    const tabs = page.getByRole("navigation", { name: "Daily Update tabs" });
    assert.equal(await tabs.getByRole("link").count(), 5);
    assert.equal(await page.locator("aside").getByRole("link", { name: "Daily Update", exact: true }).count(), 1);
    assert.equal(await page.getByLabel("From date", { exact: true }).isVisible(), false);
    assert.equal(await page.getByLabel("Employee CRM ID", { exact: true }).count(), 0);
    for (const area of ["follow-ups", "progress"]) {
      if (area === "progress") await tabs.getByRole("link", { name: names[1], exact: true }).click();
      await page.getByRole("button", { name: "+ Add record", exact: true }).click();
      const dialog = page.getByRole("dialog");
      assert.equal(await dialog.getByLabel("Employee name", { exact: true }).getAttribute("list") !== null, true);
      await dialog.getByLabel("Employee name", { exact: true }).fill("Synthetic manual name");
      await dialog.getByLabel("Customer name", { exact: true }).fill(`Synthetic ${area} customer`);
      await dialog.getByLabel("Customer number", { exact: true }).fill("9000000000");
      await dialog.getByLabel("Loan type", { exact: true }).fill("Personal Loan");
      await dialog.getByLabel("Bank / NBFC", { exact: true }).fill("Synthetic Bank");
      if (area === "follow-ups") await dialog.getByLabel("Today's case status / remarks", { exact: true }).fill("Documents requested");
      else {
        await dialog.getByLabel("Today's case stage", { exact: true }).fill("Application login");
        await dialog.getByLabel("What's next?", { exact: true }).fill("Call the bank tomorrow");
      }
      assert.equal(await dialog.getByLabel(/LEAD ID|CRM ID/).count(), 0);
      if (area === "follow-ups") await page.screenshot({ path: resolve(output, `${role}-${width}-entry-form.png`), fullPage: true });
      await dialog.getByRole("button", { name: "Save record", exact: true }).click();
      await dialog.waitFor({ state: "hidden" });
      let row = page.getByRole("row").filter({ hasText: `Synthetic ${area} customer` });
      await row.waitFor();
      await row.getByRole("button", { name: "Edit", exact: true }).click();
      if (area === "follow-ups") await dialog.getByLabel("Today's case status / remarks", { exact: true }).fill("Second update saved");
      else await dialog.getByLabel("What's next?", { exact: true }).fill("Second bank update saved");
      await dialog.getByRole("button", { name: "Save changes", exact: true }).click();
      await dialog.waitFor({ state: "hidden" });
      row = page.getByRole("row").filter({ hasText: `Synthetic ${area} customer` });
      await row.getByText(area === "follow-ups" ? "Second update saved" : "Second bank update saved", { exact: true }).waitFor();
      if (role === "owner") assert.equal(await row.getByRole("button", { name: "Delete", exact: true }).count(), 1);
      else assert.equal(await row.getByRole("button", { name: "Delete", exact: true }).count(), 0);
      if (area === "progress") await page.screenshot({ path: resolve(output, `${role}-${width}-progress.png`), fullPage: true });
      if (role === "owner") {
        await row.getByRole("button", { name: "Delete", exact: true }).click();
        await page.getByRole("button", { name: "Delete record", exact: true }).click();
        await row.waitFor({ state: "hidden" });
      }
    }
    await tabs.getByRole("link", { name: names[2], exact: true }).click();
    await page.getByRole("heading", { name: names[2], exact: true }).waitFor();
    await page.getByText("Synthetic Employee", { exact: true }).last().waitFor();
    if (role === "employee") {
      assert.equal(await page.getByRole("button", { name: "Edit", exact: true }).count(), 0);
      assert.equal(await page.getByRole("button", { name: "Delete", exact: true }).count(), 0);
      await page.getByRole("button", { name: "Request correction", exact: true }).click();
      await page.getByLabel("What needs correcting?", { exact: true }).fill("Synthetic missing logout correction");
      await page.getByRole("button", { name: "Send request", exact: true }).click();
      await page.getByRole("dialog").waitFor({ state: "hidden" });
      assert.equal(rows.issues.length, 1);
    }
    await tabs.getByRole("link", { name: names[4], exact: true }).click();
    await page.getByRole("heading", { name: names[4], exact: true }).waitFor();
    assert.equal(await page.getByLabel("Column mapping (JSON: uploaded heading to destination field)", { exact: true }).isVisible(), false);
    assert.deepEqual(errors, []);
    evidence.push({ role, width, defaultTabs: 5, nameDropdownAndManualEntry: "PASS", manualFollowUpAndProgressAddEdit: "PASS", ownerOnlyDelete: "PASS", sessionProtection: "PASS", pageErrors: errors, writes });
    await context.close();
  }
  await writeFile(resolve(output, "evidence.json"), JSON.stringify({ fixtures: "Synthetic local API responses; real UI interactions, not production persistence evidence", checks: evidence }, null, 2));
  console.log(JSON.stringify({ status: "PASS", scenarios: evidence.length, output }));
} finally { await browser.close(); }
