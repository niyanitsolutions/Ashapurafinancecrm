import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ArticleEvaluation, KnowledgeImport } from "./TrainingWorkbench";
import { evaluateKnowledge, importKnowledge } from "./api";

vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "operator" }) }));
vi.mock("./api", () => ({ evaluateKnowledge: vi.fn(), importKnowledge: vi.fn(), getEvaluations: vi.fn() }));
const article = { id: "article", version: 3, title: "EMI policy", content: "Reviewed EMI reconciliation policy", status: "review", language: "en", effective_on: null, expires_on: null, revisions: [] };
function mount(component: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{component}</QueryClientProvider>); }
describe("Governed knowledge ingestion and evidence evaluation", () => {
  beforeEach(() => vi.clearAllMocks());
  it("imports into draft and explicitly labels unsupported processing", async () => {
    vi.mocked(importKnowledge).mockResolvedValue({ ...article, status: "draft" }); mount(<KnowledgeImport />);
    fireEvent.change(screen.getByLabelText("Document title"), { target: { value: "EMI policy" } });
    fireEvent.change(screen.getByLabelText("Knowledge file"), { target: { files: [new File(["Reviewed EMI evidence"], "policy.txt", { type: "text/plain" })] } });
    // Construct FormData's file explicitly: jsdom doesn't propagate a synthetic FileList.
    const OriginalFormData = FormData;
    vi.spyOn(globalThis, "FormData").mockImplementation(function(form?: HTMLFormElement) { const data = new OriginalFormData(form); data.set("file", new File(["Reviewed EMI evidence"], "policy.txt", { type: "text/plain" })); return data; });
    fireEvent.submit(screen.getByRole("button", { name: "Import as draft" }).closest("form")!);
    await waitFor(() => expect(importKnowledge).toHaveBeenCalled());
    expect(await screen.findByText(/imported as draft/)).toBeInTheDocument(); expect(screen.getByText(/malware scanning is unavailable/)).toBeInTheDocument(); vi.restoreAllMocks();
  });
  it("pins evaluation to article version and exposes missing facts without claiming model quality", async () => {
    vi.mocked(evaluateKnowledge).mockResolvedValue({ id: "evaluation", evaluated_version: 3, passed: false, kind: "lexical_evidence_only", latency_ms: 2, semantic_groundedness: "not_evaluated", prompt_injection_resistance: "not_evaluated", cases: [{ question: "What EMI evidence?", required_facts: ["verified payment"], expect_evidence: true, passed: false, missing_facts: ["verified payment"], excerpts: [] }] });
    mount(<ArticleEvaluation article={article} editable />);
    fireEvent.click(screen.getByText("Evaluate draft evidence and view reports")); fireEvent.change(screen.getByLabelText("Evaluation question"), { target: { value: "What EMI evidence?" } }); fireEvent.change(screen.getByLabelText(/Required facts/), { target: { value: "verified payment" } }); fireEvent.click(screen.getByRole("button", { name: "Evaluate current draft" }));
    await waitFor(() => expect(evaluateKnowledge).toHaveBeenCalledWith(article, [{ question: "What EMI evidence?", required_facts: ["verified payment"], expect_evidence: true }]));
    expect(await screen.findByText(/Missing: verified payment/)).toBeInTheDocument(); expect(screen.getByText(/Semantic groundedness: not_evaluated/)).toBeInTheDocument();
  });
  it("does not expose mutation controls to a read-only reviewer", () => {
    mount(<ArticleEvaluation article={article} editable={false} />); expect(screen.queryByRole("button", { name: "Evaluate current draft" })).not.toBeInTheDocument();
  });
});
