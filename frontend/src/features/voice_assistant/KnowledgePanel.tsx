import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/shared/api/errors";
import { articleAction, getKnowledge, saveArticle, testConversation, type Article, type ConsoleResult } from "./api";
import { ArticleEvaluation, KnowledgeImport } from "./TrainingWorkbench";
import { PolicyStudio } from "./PolicyStudio";

export function KnowledgePanel() {
  const { userId } = useAuth(); const { can } = usePermissions(); const client = useQueryClient();
  const [page, setPage] = useState(1); const [editing, setEditing] = useState<Article | null>(null);
  const [title, setTitle] = useState(""); const [content, setContent] = useState(""); const [language, setLanguage] = useState("en");
  const [effective, setEffective] = useState(""); const [expires, setExpires] = useState("");
  const [question, setQuestion] = useState(""); const [result, setResult] = useState<ConsoleResult | null>(null);
  const [history, setHistory] = useState<{ role: string; content: string }[]>([]);
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const allowed = can("voice_assistant:knowledge", "view");
  const articles = useQuery({ queryKey: ["voice", userId, "knowledge", page], queryFn: () => getKnowledge(page), enabled: allowed });
  async function change(article: Article, action: string, target?: number) {
    setBusy(true); setError(null);
    try { await articleAction(article, action, target); await client.invalidateQueries({ queryKey: ["voice", userId, "knowledge"] }); }
    catch (e) { setError(getErrorMessage(e)); } finally { setBusy(false); }
  }
  if (!allowed) return <p>You need the voice knowledge View permission.</p>;
  return <div className="space-y-6">
    <ErrorBanner message={error ?? (articles.error ? getErrorMessage(articles.error) : null)} />
    <p className="text-sm text-text/70">Knowledge supplies reviewed facts. It does not fine-tune a model. Editing a published article preserves its approved release until a revision is explicitly published or archived.</p>
    {can("voice_assistant:knowledge", "create") && <KnowledgeImport key={userId} />}
    {(editing ? can("voice_assistant:knowledge", "edit") : can("voice_assistant:knowledge", "create")) && <form className="bg-card rounded-xl border p-5 space-y-3" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError(null);
      try { await saveArticle({ title, content, language, effective_on: effective || null, expires_on: expires || null, version: editing?.version ?? 1 }, editing?.id); setEditing(null); setTitle(""); setContent(""); await client.invalidateQueries({ queryKey: ["voice", userId, "knowledge"] }); }
      catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
    }}>
      <h2 className="font-semibold">{editing ? "Edit knowledge (returns to draft)" : "New knowledge article"}</h2>
      <label className="block">Title<input required minLength={3} maxLength={150} className="block border rounded-lg p-2 w-full" value={title} onChange={e => setTitle(e.target.value)} /></label>
      <label className="block">Approved business content<textarea required minLength={20} maxLength={50000} rows={6} className="block border rounded-lg p-2 w-full" value={content} onChange={e => setContent(e.target.value)} /></label>
      <div className="flex flex-wrap gap-3"><label>Content language code<input pattern="[a-z]{2}" maxLength={2} className="block border rounded-lg p-2" value={language} onChange={e => setLanguage(e.target.value)} /></label><label>Effective date<input type="date" className="block border rounded-lg p-2" value={effective} onChange={e => setEffective(e.target.value)} /></label><label>Expiry date<input type="date" className="block border rounded-lg p-2" value={expires} onChange={e => setExpires(e.target.value)} /></label></div>
      <Button type="submit" loading={busy}>Save draft</Button>{editing && <Button variant="ghost" onClick={() => { setEditing(null); setTitle(""); setContent(""); }}>Cancel editing</Button>}
    </form>}
    <section className="space-y-3" aria-label="Knowledge library">
      {articles.isPending && <p role="status">Loading knowledge…</p>}
      {articles.data?.items.length === 0 && <p>No knowledge articles yet.</p>}
      {articles.data?.items.map(article => <article key={article.id} className="bg-card rounded-xl border p-4"><h3 className="font-semibold">{article.title}</h3><p className="text-sm my-2">{article.status} · v{article.version} · {article.language}</p>
        {article.publication && <p className="text-sm">Active approved publication: v{article.publication.version}</p>}
        {article.source && <p className="text-sm">Imported {article.source.format.toUpperCase()} · Scan: {article.source.scan_status}</p>}
        <details className="my-3"><summary className="cursor-pointer text-primary">Review content and effective dates</summary><p className="my-2 text-sm">Effective: {article.effective_on ?? "immediately"} · Expires: {article.expires_on ?? "not specified"}</p><p className="whitespace-pre-wrap text-sm">{article.content}</p></details>
        <ArticleEvaluation key={`${article.id}:${article.version}`} article={article} editable={can("voice_assistant:knowledge", "edit")} />
        <div className="flex gap-2 flex-wrap">
        {can("voice_assistant:knowledge", "edit") && <Button variant="secondary" disabled={busy} onClick={() => { setEditing(article); setTitle(article.title); setContent(article.content); setLanguage(article.language); setEffective(article.effective_on ?? ""); setExpires(article.expires_on ?? ""); }}>Edit</Button>}
        {can("voice_assistant:knowledge", "approve") && <>
          {article.status === "draft" && <Button disabled={busy} onClick={() => change(article, "review")}>Submit for review</Button>}
          {article.status === "review" && <Button disabled={busy} onClick={() => change(article, "publish")}>Approve and publish</Button>}
          {article.status !== "archived" && <Button variant="secondary" disabled={busy} onClick={() => change(article, "archive")}>Archive</Button>}
          {article.revisions.length > 0 && <Button variant="secondary" disabled={busy} onClick={() => change(article, "rollback", article.revisions.at(-1)?.version)}>Restore previous content to draft</Button>}
          {article.publications && article.publications.filter(p => p.version !== article.publication?.version).map(p => <Button key={p.version} variant="secondary" disabled={busy} onClick={() => change(article, "rollback_published", p.version)}>Activate approved publication v{p.version}</Button>)}
        </>}
      </div></article>)}
      <div className="flex gap-3"><Button variant="secondary" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</Button><span>Page {page}</span><Button variant="secondary" disabled={page * 25 >= (articles.data?.total ?? 0)} onClick={() => setPage(p => p + 1)}>Next</Button></div>
    </section>
    <PolicyStudio />
    <form className="bg-card rounded-xl border p-5 space-y-3" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError(null);
      try { const answer = await testConversation(question, language, history.slice(-10)); setResult(answer); if (answer.response) setHistory(old => [...old, { role: "user", content: question }, { role: "assistant", content: answer.response!.slice(0, 2000) }].slice(-10)); }
      catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
    }}><h2 className="font-semibold">Conversation and retrieval test console</h2><p className="text-sm text-text/70">Dynamic text responses require an administrator-configured local model. Language codes here describe text; no speech languages have been validated.</p>
      <label className="block">Natural-language question<textarea required minLength={2} maxLength={2000} className="block border rounded-lg p-2 w-full" value={question} onChange={e => setQuestion(e.target.value)} /></label><Button type="submit" loading={busy}>Test question</Button><Button variant="ghost" onClick={() => { setHistory([]); setResult(null); }}>Reset conversation</Button>
      {history.length > 0 && <p className="text-sm">{history.length / 2} conversation turns retained in this browser view.</p>}
      {result?.policy && <div role="status" className="text-sm border rounded-lg p-3"><p>Intent: {result.policy.intent.replaceAll("_", " ")} · Confidence: {result.policy.confidence ?? "Unavailable"}</p><p>Proposed next action: {result.policy.next_action.replaceAll("_", " ")} · {result.policy.reason.replaceAll("_", " ")}</p><p>Backend actions disabled · Caller unverified · Policy {result.policy.policy_version}</p></div>}
      {result && <div aria-live="polite" className="space-y-3"><p>{result.mode} · {result.language} · {result.uncertain ? "Review required" : "Generated response"}{result.escalate ? " · Human escalation suggested" : ""}</p>{result.response && <p className="whitespace-pre-wrap">{result.response}</p>}{result.warnings.map(w => <p className="text-sm text-text/70" key={w}>{w}</p>)}{result.sources.map((source, i) => <blockquote className="border-l-2 border-primary pl-3" key={`${source.id}-${i}`}><strong>{source.title} · v{source.version}</strong><p className="text-sm">{source.excerpt}</p></blockquote>)}{!result.sources.length && <p>No relevant current published source found.</p>}</div>}
    </form>
  </div>;
}
