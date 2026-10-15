// Inventory the real TypeScript router without changing routes or permissions.
import ts from "../frontend/node_modules/typescript/lib/typescript.js";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const path = "frontend/src/app/router.tsx";
const source = ts.createSourceFile(path, await readFile(path, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const imports = new Map();
for (const statement of source.statements) {
  if (ts.isImportDeclaration(statement) && statement.importClause?.namedBindings && ts.isNamedImports(statement.importClause.namedBindings)) {
    for (const item of statement.importClause.namedBindings.elements) imports.set(item.name.text, statement.moduleSpecifier.text);
  }
}
const rows = [];
function prop(node, name) { return node.properties.find(p => ts.isPropertyAssignment(p) && p.name.getText(source).replaceAll('"', "") === name)?.initializer; }
function walk(array, parent = "", guards = []) {
  for (const node of array.elements) {
    if (!ts.isObjectLiteralExpression(node)) throw new Error("Dynamic route entry needs manual inventory.");
    const segment = prop(node, "path"); const element = prop(node, "element"); const children = prop(node, "children");
    const value = segment && ts.isStringLiteral(segment) ? segment.text : "";
    const full = value.startsWith("/") ? value : [parent.replace(/\/$/, ""), value].filter(Boolean).join("/") || "/";
    const jsx = element && (ts.isJsxSelfClosingElement(element) ? element : ts.isJsxElement(element) ? element.openingElement : null);
    const component = jsx?.tagName.getText(source) ?? element?.getText(source) ?? "";
    const newGuards = /^Require/.test(component) ? [...guards, element.getText(source)] : guards;
    if (component && !/^Require/.test(component)) rows.push({ full, component, file: imports.get(component) ?? "inline", guards: newGuards, line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1 });
    if (children) { if (!ts.isArrayLiteralExpression(children)) throw new Error("Dynamic route children need manual inventory."); walk(children, full, newGuards); }
  }
}
function find(node) { if (ts.isCallExpression(node) && node.expression.getText(source) === "createBrowserRouter") { if (!ts.isArrayLiteralExpression(node.arguments[0])) throw new Error("Expected static route tree."); walk(node.arguments[0]); } ts.forEachChild(node, find); }
find(source);
if (!rows.length) throw new Error("Router inventory must not be empty.");
const clean = text => text.replaceAll("|", "\\|").replace(/\s+/g, " ");
const entries = [];
for (const row of rows) {
  let shared = "layout/redirect";
  if (row.file.startsWith("@/")) {
    const file = resolve("frontend/src", row.file.slice(2) + ".tsx");
    const body = await readFile(file, "utf8");
    shared = ["SimplePageLayout", "Card", "Button", "DataTable", "CaseListPage", "FormField", "ModuleTabs"].filter(name => body.includes(name)).join(", ") || "global tokens; custom page structure";
  }
  entries.push(`| ${clean(row.full)} | ${clean(row.component)} | ${clean(row.file)} | ${clean(shared)} | ${clean(row.guards.join(" → ") || "public / inherited application routing")} |`);
}
await writeFile("docs/CRM_ROUTE_INVENTORY.md", `# CRM route and shared UI coverage\n\nGenerated from the actual TypeScript AST in ${path} at the current checkout.\n${rows.length} rendered route/layout/redirect entries; pathless layouts share their parent path.\nNo route or authorization was changed. Global content tokens apply across the CRM;\nshared-component adoption does not certify a bespoke redesign or browser acceptance\nfor every page. Screenshot coverage and remaining per-page work are reported separately.\nVoice's :section route also dispatches existing panels internally; see VoiceAssistantPage.\n\n| Route | Component | Source import | Shared content components | Inherited guards |\n|---|---|---|---|---|\n${entries.join("\n")}\n`);
console.log(`Inventoried ${rows.length} route/layout/redirect entries.`);
