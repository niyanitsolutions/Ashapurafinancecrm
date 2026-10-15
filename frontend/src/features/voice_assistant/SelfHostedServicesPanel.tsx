import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/useAuth";
import { Button } from "@/components/buttons/Button";
import { Card, CardHeader } from "@/components/cards/Card";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { getErrorMessage } from "@/shared/api/errors";
import { getSelfHostedHealth, testSelfHostedText } from "./api";

export function SelfHostedServicesPanel() {
  const { role, userId } = useAuth(); const cache = useQueryClient(); const key = ["voice", userId, "self-hosted-health"];
  const query = useQuery({ queryKey: key, queryFn: getSelfHostedHealth, enabled: role === "owner" });
  const mutation = useMutation({ mutationFn: testSelfHostedText, onSuccess: data => cache.setQueryData(key, data) });
  if (role !== "owner") return null;
  return <Card><CardHeader title="Self-hosted AI service readiness" subtitle="Business-controlled services · no external AI API key required" />
    <ErrorBanner message={query.error || mutation.error ? getErrorMessage(query.error ?? mutation.error) : null} />
    {query.isPending && <p role="status">Loading self-hosted service status...</p>}
    {query.data && <><dl className="grid gap-4 sm:grid-cols-3 text-sm"><div><dt className="text-textSecondary">Text inference</dt><dd className="font-semibold">{query.data.text_inference.replaceAll("_", " ")}</dd><dd>{query.data.model ?? "No model configured"}</dd></div><div><dt className="text-textSecondary">Speech recognition</dt><dd>{query.data.speech_to_text.replaceAll("_", " ")}</dd></div><div><dt className="text-textSecondary">Speech synthesis</dt><dd>{query.data.text_to_speech.replaceAll("_", " ")}</dd></div></dl><p className="mt-4 text-sm text-textSecondary">{query.data.message}</p>
      {query.data.last_test && <p className="my-3 text-xs">Last text test: {query.data.last_test.status}; {query.data.last_test.latency_ms} ms. Evidence: {query.data.evidence_fresh ? "within 15 minutes" : "stale"}.</p>}
      <Button className="mt-4" variant="secondary" disabled={mutation.isPending || !query.data.configured} onClick={() => mutation.mutate()}>Test representative text request</Button><p className="mt-2 text-xs text-textSecondary">Runs a synthetic structured-text request against the operator-configured model. It does not download models, use customer data, test speech, or enable live calls.</p>
    </>}
  </Card>;
}
