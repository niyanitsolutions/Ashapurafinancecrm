// Local-only visual regression harness. Synthetic browser responses are never
// installed in the application or used as backend/telephony acceptance evidence.
import { chromium } from "../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const phase = process.argv[2] ?? "before";
if (!["before", "after"].includes(phase)) throw new Error("Use before or after.");
const output = resolve("docs/screenshots/voice-upgrade", phase);
await mkdir(output, { recursive: true });
const origin = "http://127.0.0.1:5173";
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const evidence = [];
const navKeys = ["dashboard", "leads", "loan_cases", "insurance_cases", "invoices", "voice_assistant", "referral_partners", "reports", "messaging", "support_tickets", "integrations", "employees", "roles", "settings", "owner_accounts"];
const response = (data, meta = null) => ({ success: true, data, error: null, meta });
try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, deviceScaleFactor: 1, reducedMotion: "reduce" });
    await context.addInitScript(() => localStorage.setItem("afs_refresh_token", "synthetic-visual-fixture-only"));
    await context.route("**/*", async route => {
      const request = route.request(); const url = new URL(request.url());
      const path = url.pathname.replace(/^.*\/api\/v1/, "");
      if (url.pathname.includes("/api/v1/")) {
        let data = [];
        if (path === "/auth/refresh") data = { access_token: "synthetic-visual-access-only", refresh_token: "synthetic-visual-fixture-only" };
        else if (path === "/auth/profile") data = { user_id: "aaaaaaaaaaaaaaaaaaaaaaaa", role: "owner", mobile: "9000000000", name: "Preview Owner", must_change_password: false };
        else if (path === "/owner/me") data = { id: "bbbbbbbbbbbbbbbbbbbbbbbb", owner_type: "primary", full_name: "Preview Owner", display_name: "Preview Owner", is_primary: true };
        else if (path === "/dashboard/nav") data = navKeys.map((key, order) => ({ key, label: key, route: "/", icon: null, order }));
        else if (path.includes("unread-count")) data = { count: 0 };
        else if (path === "/voice-assistant/dashboard") data = { metrics: { total: 0, queued: 0, completed: 0, failed: 0 }, worker: "unverified", recent: [], provider: { selected_provider: "none", blockers: ["No verified telephony or speech service"], sandbox: "not_configured" } };
        else if (path === "/voice-assistant/campaigns") data = { items: [], total: 0, page: 1, production_dispatch: "blocked" };
        else if (path === "/voice-assistant/self-hosted/status") data = { text_inference: "disabled", model: null, configured: false, evidence_fresh: false, speech_to_text: "not_installed", text_to_speech: "not_installed", live_calling: false, message: "Synthetic browser fixture: no live AI service verified.", last_test: null };
        else if (path.startsWith("/voice-assistant/native")) data = { items: [], total: 0, live_calling: false };
        else if (path === "/invoices") data = { items: [], total: 0, page: 1, total_pages: 1 };
        else if (path.includes("counts")) data = {};
        else if (path === "/owner/registration-status") data = { is_registered: true };
        return route.fulfill({ json: response(data, { pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 } }) });
      }
      if (url.origin === origin) return route.continue();
      return route.abort("blockedbyclient");
    });
    const cases = [["campaigns", "/voice-assistant/campaigns"], ["invoices", "/invoices"], ["leads", "/leads"]];
    if (phase === "after") cases.push(["native-connections", "/voice-assistant/providers"]);
    for (const [name, path] of cases) {
      const page = await context.newPage(); const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(origin + path, { waitUntil: "networkidle" });
      await page.screenshot({ path: resolve(output, `${name}-${width}.png`), fullPage: true });
      const measurements = await page.evaluate(() => {
        const sidebar = document.querySelector("aside"); const link = sidebar?.querySelector("a[aria-current=page]");
        return { title: document.title, headings: [...document.querySelectorAll("h1,h2")].map(el => el.textContent), overflow: document.documentElement.scrollWidth > innerWidth, sidebarStyles: sidebar ? { boxShadow: getComputedStyle(sidebar).boxShadow, activeShadow: link ? getComputedStyle(link).boxShadow : null, activeFont: link ? getComputedStyle(link).font : null } : null, sidebar: sidebar ? { width: sidebar.getBoundingClientRect().width, color: getComputedStyle(sidebar).backgroundColor, activeColor: link ? getComputedStyle(link).backgroundColor : null, links: [...sidebar.querySelectorAll("a")].map(el => ({ label: el.textContent, href: el.getAttribute("href") })) } : null };
      });
      const overflowNodes = await page.evaluate(() => [...document.querySelectorAll("main *")].map(el => ({ element: el.tagName, className: String(el.className), width: el.getBoundingClientRect().width, right: el.getBoundingClientRect().right })).filter(item => item.right > innerWidth + 1).slice(0, 12));
      evidence.push({ phase, name, width, synthetic: true, errors, ...measurements, overflowNodes });
      await page.close();
    }
    await context.close();
  }
  await writeFile(resolve(output, "evidence.json"), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence.map(({ name, width, errors, overflow, headings }) => ({ name, width, errors, overflow, headings }))));
} finally { await browser.close(); }
