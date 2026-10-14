import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/shared/api/errors";
import { evaluateKnowledge, getEvaluations, importKnowledge, type Article, type KnowledgeEvaluation } from "./api";

export function KnowledgeImport() {
  const { userId } = useAuth(); const client = useQueryClient();
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  return <form className="bg-card rounded-xl border p-5 space-y-3" onSubmit={async event => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    const file = data.get("file");
    if (!(file instanceof File) || file.size > 5 * 1024 * 1024) { setError("Choose a file no larger than 5 MB."); return; }
    setBusy(true); setError(null); setMessage("");
    try {
      const article = await importKnowledge(data); form.reset();
      setMessage(`${article.title} imported as draft. Review, evaluate and approve before publication.`);
      await client.invalidateQueries({ queryKey: ["voice", userId, "knowledge"] });
    } catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
  }}>
    <h2 className="font-semibold">Import knowledge document</h2>
    <p className="text-sm">TXT, CSV, DOCX and XLSX · 5 MB · 50,000 extracted characters. No formulas, macros, external links or embedded objects. Files are parsed without execution; malware scanning is unavailable. PDF, website import, embeddings and automatic fine-tuning are unavailable.</p>
    <ErrorBanner message={error} />
    <label className="block">Document title<input name="title" required minLength={3} maxLength={150} className="block border rounded-lg p-2 w-full" /></label>
    <label className="block">Document language<input name="language" defaultValue="en" required pattern="[a-z]{2}" maxLength={2} className="block border rounded-lg p-2" /></label>
    <label className="block">Knowledge file<input name="file" required type="file" accept=".txt,.csv,.docx,.xlsx" className="block mt-2" /></label>
    <Button type="submit" loading={busy}>Import as draft</Button>
    {message && <p role="status">{message}</p>}
  </form>;
}

export function ArticleEvaluation({ article, editable }: { article: Article; editable: boolean }) {
  const [question, setQuestion] = useState(""); const [facts, setFacts] = useState("");
  const [negative, setNegative] = useState(false); const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null); const [reports, setReports] = useState<KnowledgeEvaluation[]>([]);
  return <details className="my-3 border-t pt-3">
    <summary className="cursor-pointer text-primary">Evaluate draft evidence and view reports</summary>
    <p className="text-sm my-2">Tests use draft lexical retrieval and literal required facts. They do not certify generated answers, financial accuracy, multilingual quality or prompt-injection resistance. Imported documents require a passing evaluation before publication.</p>
    <ErrorBanner message={error} />
    {editable && <form className="space-y-3" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError(null);
      try {
        const report = await evaluateKnowledge(article, [{ question, expect_evidence: !negative, required_facts: negative ? [] : facts.split("\n").map(f => f.trim()).filter(Boolean) }]);
        setReports(old => [report, ...old].slice(0, 10));
      } catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
    }}>
      <label className="block">Evaluation question<input required minLength={2} maxLength={2000} value={question} onChange={e => setQuestion(e.target.value)} className="block border rounded-lg p-2 w-full" /></label>
      <label className="block"><input type="checkbox" checked={negative} onChange={e => setNegative(e.target.checked)} /> Expect no relevant evidence</label>
      {!negative && <label className="block">Required facts (one per line; up to 10)<textarea required maxLength={2010} rows={3} value={facts} onChange={e => setFacts(e.target.value)} className="block border rounded-lg p-2 w-full" /></label>}
      <Button type="submit" loading={busy}>Evaluate current draft</Button>
    </form>}
    <Button variant="secondary" disabled={busy} className="my-3" onClick={async () => {
      setBusy(true); setError(null);
      try { setReports(await getEvaluations(article.id)); } catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
    }}>Load recent evaluations</Button>
    {reports.map(report => <div key={report.id} className="border rounded-lg p-3 my-2" aria-live="polite">
      <p>v{report.evaluated_version} · {report.passed ? "Evidence checks passed" : "Evidence checks failed"} · {report.latency_ms} ms</p>
      <p className="text-sm">Semantic groundedness: {report.semantic_groundedness} · Injection resistance: {report.prompt_injection_resistance}</p>
      {report.cases.map((item, i) => <div key={i} className="text-sm mt-2"><strong>{item.question}</strong><p>{item.passed ? "Pass" : "Fail"}{item.missing_facts.length ? ` · Missing: ${item.missing_facts.join(", ")}` : ""}</p>{item.excerpts.map((text, index) => <blockquote className="border-l-2 pl-2 my-2" key={index}>{text}</blockquote>)}</div>)}
    </div>)}
  </details>;
}
