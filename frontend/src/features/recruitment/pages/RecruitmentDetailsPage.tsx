import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge } from "@/components/badges/Badge";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Icon } from "@/theme/icons";
import {
  getRecruitmentLead,
  getRecruitmentLeadAdvisor,
  getRecruitmentTimeline,
  type AdvisorSummary,
  type RecruitmentLeadDetail,
  type RecruitmentTimelineEntry,
} from "@/features/recruitment/api";
import {
  DocumentCollectionPanel,
  ExaminationHistoryPanel,
  InfoRow,
  Panel,
  PersonalInfoPanel,
} from "@/features/recruitment/components/RecruitmentInfoPanels";
import { STAGE_LABELS, activityLabel } from "@/features/recruitment/labels";
import { getErrorMessage } from "@/shared/api/errors";
import { formatISTDateTime } from "@/shared/dateFormat";

export function RecruitmentDetailsPage() {
  const { recruitmentId = "" } = useParams();
  const [lead, setLead] = useState<RecruitmentLeadDetail | null>(null);
  const [timeline, setTimeline] = useState<RecruitmentTimelineEntry[]>([]);
  const [advisor, setAdvisor] = useState<AdvisorSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getRecruitmentLead(recruitmentId)
      .then((data) => {
        setLead(data);
        if (data.advisor_id) getRecruitmentLeadAdvisor(recruitmentId).then(setAdvisor).catch(() => undefined);
      })
      .catch((err) => setError(getErrorMessage(err)));
    getRecruitmentTimeline(recruitmentId)
      .then(setTimeline)
      .catch(() => undefined);
  }, [recruitmentId]);

  useEffect(() => {
    load();
  }, [load]);

  if (error)
    return (
      <div className="p-6">
        <ErrorBanner message={error} />
      </div>
    );
  if (!lead) return <div className="p-6 text-sm text-textSecondary">Loading…</div>;

  return (
    <div className="p-4 lg:p-6">
      <Link
        to="/insurance-management/recruitment/fresh"
        className="mb-3 inline-flex items-center gap-1 text-sm text-textSecondary hover:text-text"
      >
        <Icon name="chevron-left" className="h-4 w-4" /> Recruitment Leads
      </Link>

      <div className="mb-4 flex items-center gap-3">
        <h1 className="text-xl font-bold text-text">{lead.full_name}</h1>
        <span className="text-sm text-textSecondary">{lead.recruitment_code}</span>
        <Badge tone={lead.stage === "rejected" ? "danger" : lead.stage === "advisor" ? "success" : "info"}>
          {STAGE_LABELS[lead.stage]}
        </Badge>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <PersonalInfoPanel lead={lead} />
        <DocumentCollectionPanel lead={lead} />
        <ExaminationHistoryPanel lead={lead} />

        {advisor && (
          <Panel title="Advisor">
            <InfoRow label="Advisor code" value={advisor.advisor_code} />
            <InfoRow label="Channel" value={advisor.channel === "qr" ? "QR" : "Non QR"} />
            <InfoRow label="Agency code" value={advisor.agency_code} />
            <InfoRow label="Status" value={advisor.status} />
          </Panel>
        )}

        <Panel title="Timeline" className="lg:col-span-2">
          {timeline.length === 0 ? (
            <p className="text-sm text-textSecondary">No activity yet.</p>
          ) : (
            <ul className="space-y-2">
              {timeline.map((entry, index) => (
                <li key={index} className="flex justify-between gap-4 text-sm">
                  <span className="text-text">
                    {entry.type === "note" ? `Note: ${entry.text}` : activityLabel(entry.event_type)}
                  </span>
                  <span className="shrink-0 text-2xs text-textSecondary">{formatISTDateTime(entry.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
