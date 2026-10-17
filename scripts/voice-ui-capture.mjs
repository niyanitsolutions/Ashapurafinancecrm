// Local-only visual regression harness. Synthetic browser responses are never
// installed in the application or used as backend/telephony acceptance evidence.
import { chromium } from "../frontend/node_modules/.cache/voice-ui-audit/node_modules/playwright/index.mjs";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const phase = process.argv[2] ?? "before";
if (!["before", "after", "platform", "callbacks", "integration"].includes(phase)) throw new Error("Use before, after, platform, callbacks or integration.");
const output = phase === "integration" ? resolve("docs/screenshots/voice-integration-2026-10-17") : phase === "callbacks" ? resolve("docs/screenshots/voice-callbacks-2026-10-16") : phase === "platform" ? resolve("docs/screenshots/voice-platform-2026-10-16") : resolve("docs/screenshots/voice-upgrade", phase);
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
        else if (path === "/voice-assistant/settings") data = { version: 1, mode: "disabled", ring_seconds: 10, transfer_seconds: 20, max_duration_seconds: 300, max_concurrent_calls: 2, daily_call_limit: 50, monthly_minute_limit: 500, calls_per_minute: 5, retry_limit: 1, retry_interval_seconds: 3600, queue_timeout_seconds: 120, max_queue_length: 10, ai_fallback: true, timezone: "Asia/Kolkata", calling_start: "09:00", calling_end: "18:00", holidays: [], primary_employee_id: null, conversation_instructions: "Be concise and offer human help.", operational_rules: "Use approved knowledge only.", default_language: "en" };
        else if (path === "/voice-assistant/platform/speech-profiles") data = { profiles: [], message: "No approved speech profiles. Install pinned engines and models through the reviewed deployment procedure." };
        else if (/\/voice-assistant\/platform\/(test|production)$/.test(path)) data = { environment: path.split("/").at(-1), version: 1, emergency_stopped: true, inbound: false, outbound: false, processing: false, production_eligible: false, live_implementation_available: false, evidence_token: "a".repeat(64), history: [], components: Object.fromEntries(["telephony", "stt", "tts", "inference", "media", "workers", "recording", "transfer", "smartflo"].map(key => [key, { enabled: false, profile_id: null, testing_supported: !["media", "recording", "transfer"].includes(key) }])), gates: [{ key: "native_control_media", passed: false, remediation: "Deployed PBX version and actual bidirectional media require verification." }, { key: "operator_number_routing", passed: false, remediation: "Approved telecom trunk and authorized number routing are required." }, { key: "speech_pipeline", passed: false, remediation: "Approved models and actual end-to-end audio acceptance required." }] };
        else if (path.includes("/platform/") && path.endsWith("/speech-tests")) data = { items: [], total: 0 };
        else if (path === "/voice-assistant/self-hosted/status") data = { text_inference: "disabled", model: null, configured: false, evidence_fresh: false, speech_to_text: "not_installed", text_to_speech: "not_installed", live_calling: false, message: "Synthetic browser fixture: no live AI service verified.", last_test: null };
        else if (path.startsWith("/voice-assistant/native")) data = { items: [], total: 0, live_calling: false };
        else if (path === "/invoices") data = { items: [], total: 0, page: 1, total_pages: 1 };
        else if (/^\/leads\/[a-f0-9]{24}$/.test(path)) data = { id: "bbbbbbbbbbbbbbbbbbbbbbbb", lead_code: "AFS-LEAD-PREVIEW", full_name: "Synthetic preview lead", mobile: "9000000000", email: null, source_id: "cccccccccccccccccccccccc", source_name: "Preview fixture", product_category: "loan", product_id: "dddddddddddddddddddddddd", product_name: "Preview product", assigned_to: "eeeeeeeeeeeeeeeeeeeeeeee", assigned_to_name: "Preview Supervisor", status: "active", stage: "assigned", salary_in_hand: null, next_follow_up_date: null, assigned_by: null, assigned_by_name: null, assigned_at: null, rejected_reason: null, rejected_by: null, rejected_by_name: null, rejected_at: null, application_id: null, application_status: null, is_potential_duplicate: false, is_lead_less: false, created_at: "2026-10-16T00:00:00Z", updated_at: "2026-10-16T00:00:00Z", remarks: null, city: null, preferred_amount: null, duplicate_of_lead_ids: [], form_definition_id: null, product_form_data: null, financial_assessment: null, account_created: false, documents_required: 0, documents_verified: 0, documents_not_available: 0, all_documents_verified: false };
        else if (path === "/voice-assistant/callbacks/interpret-time") data = { status: "proposed", requested_local: "2026-10-19T11:00:00", timezone: "Asia/Kolkata", interpreted_date: "2026-10-19", clarification: "Synthetic preview: confirm the exact date and time before saving. Nothing has been scheduled.", requires_confirmation: true, persisted: false };
        else if (path === "/voice-assistant/console/evaluations") data = { suite_version: "public-policy-suite-v1", total: 1, items: [{ id: "synthetic-report", created_at: "2026-10-17T09:00:00Z", suite_version: "public-policy-suite-v1", policy_version: "public-conversation-v1", passed: true, activation_eligible: false, kind: "synthetic_policy_only", cases: [{ name: "unverified_loan_status", passed: true, rejected: false, expected_response_allowed: false, actual: { response_allowed: false, next_action: "request_verification", reason: "trusted_voice_identity_and_scoped_tools_unimplemented" } }] }] };
        else if (path === "/voice-assistant/knowledge") data = { items: [], total: 0 };
        else if (path === "/leads/lookup") data = { sources: [], loan_products: [], insurance_products: [], employees: [] };
        else if (path === "/employees") data = [{ id: "eeeeeeeeeeeeeeeeeeeeeeee", display_name: "Preview Supervisor", status: "active" }];
        else if (path === "/voice-assistant/callbacks") data = { items: [{ id: "aaaaaaaaaaaaaaaaaaaaaaaa", version: 2, state: "blocked", due_at: "2026-10-17T05:30:00Z", requested_local: "2026-10-17T11:00:00", timezone: "Asia/Kolkata", environment: "test", entity_type: "lead", entity_id: "bbbbbbbbbbbbbbbbbbbbbbbb", customer_id: "cccccccccccccccccccccccc", customer_request: "Please call tomorrow at 11 AM. Synthetic preview only.", provenance: "staff_attested", source_call_id: null, confirmed_at: "2026-10-16T00:00:00Z", blockers: ["Native live dispatch is not implemented or verified."], calls_placed: 0, history_count: 2 }], total: 1, capabilities: { create: true, edit: true, current_employee_id: "eeeeeeeeeeeeeeeeeeeeeeee" }, live_dispatch: "blocked" };
        else if (path.includes("counts")) data = {};
        else if (path === "/owner/registration-status") data = { is_registered: true };
        return route.fulfill({ json: response(data, { pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 } }) });
      }
      if (url.origin === origin) return route.continue();
      return route.abort("blockedbyclient");
    });
    const cases = phase === "integration" ? [["callback-time", "/leads/bbbbbbbbbbbbbbbbbbbbbbbb"], ["policy-studio", "/voice-assistant/knowledge"]] : phase === "callbacks" ? [["lead-callbacks", "/leads/bbbbbbbbbbbbbbbbbbbbbbbb"]] : phase === "platform" ? [["platform-settings", "/voice-assistant/settings"]] : [["campaigns", "/voice-assistant/campaigns"], ["invoices", "/invoices"], ["leads", "/leads"]];
    if (phase === "after") cases.push(["native-connections", "/voice-assistant/providers"]);
    for (const [name, path] of cases) {
      const page = await context.newPage(); const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(origin + path, { waitUntil: ["platform", "callbacks", "integration"].includes(phase) ? "domcontentloaded" : "networkidle", timeout: 60000 });
      if (phase === "platform") await page.getByRole("heading", { name: "Self-hosted platform controls" }).waitFor({ timeout: 60000 });
      if (phase === "callbacks" || name === "callback-time") {
        await page.getByRole("button", { name: "Schedule or review AI callbacks" }).click({ timeout: 60000 });
        await page.getByRole("heading", { name: "Record customer callback request" }).waitFor({ timeout: 60000 });
        await page.getByText("Staff-attested request", { exact: false }).waitFor();
      }
      if (name === "callback-time") {
        await page.getByLabel("Customer callback preference").fill("Call tomorrow at 11 AM");
        await page.getByRole("button", { name: "Preview requested time" }).click();
        await page.getByRole("button", { name: "Use proposed time in form" }).waitFor();
      }
      if (name === "policy-studio") {
        await page.getByRole("button", { name: "Load policy test reports" }).click();
        await page.getByText("Policy checks passed", { exact: false }).waitFor();
        await page.getByText("Scenario results (1)", { exact: true }).click();
      }
      if (name === "policy-studio") await page.getByRole("region", { name: "Synthetic policy regression" }).screenshot({ path: resolve(output, `${name}-${width}-detail.png`) });
      if (name === "callback-time") await page.getByRole("button", { name: "Preview requested time" }).locator("..").screenshot({ path: resolve(output, `${name}-${width}-detail.png`) });
      if (phase === "integration") await page.evaluate(async () => { window.scrollTo(0, 0); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); });
      await page.screenshot({ path: resolve(output, `${name}-${width}.png`), fullPage: true });
      if (["platform", "callbacks", "integration"].includes(phase)) await page.screenshot({ path: resolve(output, `${name}-${width}-viewport.png`) });
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
