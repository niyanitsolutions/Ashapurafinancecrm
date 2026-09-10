import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge } from "@/components/badges/Badge";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import { Icon } from "@/theme/icons";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getAdvisor, type AdvisorDetail } from "@/features/recruitment/api";
import { AddBusinessModal } from "@/features/recruitment/components/AddBusinessModal";
import { EditAdvisorModal } from "@/features/recruitment/components/EditAdvisorModal";
import {
  DocumentCollectionPanel,
  ExaminationHistoryPanel,
  InfoRow,
  Panel,
  PersonalInfoPanel,
} from "@/features/recruitment/components/RecruitmentInfoPanels";
import {
  ADVISOR_CHANNEL_LABELS,
  ADVISOR_STATUS_LABELS,
  businessCategoryLabel,
  formatINR,
  professionLabel,
} from "@/features/recruitment/labels";
import { getErrorMessage } from "@/shared/api/errors";
import { formatISTDate } from "@/shared/dateFormat";

// Secure masked "Password" row — the backend never returns the password hash or
// plaintext (see `AdvisorDetail.has_password`, a plain boolean), so the eye toggle can
// only switch between two equally-safe representations. It NEVER recovers or displays
// the real credential; clicking it cannot leak anything the API didn't already send.
function PasswordInfoRow({ hasPassword }: { hasPassword: boolean }) {
  const [visible, setVisible] = useState(false);
  if (!hasPassword) {
    return <InfoRow label="Password" value="Not set" />;
  }
  return (
    <InfoRow
      label="Password"
      value={
        <span className="inline-flex items-center gap-1.5">
          {visible ? "Password set" : "••••••••"}
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            aria-label={visible ? "Hide password state" : "Show password state"}
            className="text-textSecondary transition-colors hover:text-text"
          >
            <Icon name={visible ? "eye-off" : "eye"} className="h-4 w-4" />
          </button>
        </span>
      }
    />
  );
}

export function AdvisorDetailsPage() {
  const { advisorId = "" } = useParams();
  const { can } = usePermissions();
  const canEdit = can("insurance_management:recruitment", "edit");

  const [advisor, setAdvisor] = useState<AdvisorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<"add" | "edit" | null>(null);

  const load = useCallback(() => {
    getAdvisor(advisorId)
      .then(setAdvisor)
      .catch((err) => setError(getErrorMessage(err)));
  }, [advisorId]);

  useEffect(() => {
    load();
  }, [load]);

  if (error)
    return (
      <div className="p-6">
        <ErrorBanner message={error} />
      </div>
    );
  if (!advisor) return <div className="p-6 text-sm text-textSecondary">Loading…</div>;

  return (
    <div className="p-4 lg:p-6">
      <Link
        to="/insurance-management/advisors"
        className="mb-3 inline-flex items-center gap-1 text-sm text-textSecondary hover:text-text"
      >
        <Icon name="chevron-left" className="h-4 w-4" /> Advisors
      </Link>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold text-text">{advisor.full_name}</h1>
        <span className="text-sm text-textSecondary">{advisor.advisor_code}</span>
        <Badge tone={advisor.channel === "qr" ? "primary" : "neutral"}>{ADVISOR_CHANNEL_LABELS[advisor.channel]}</Badge>
        <Badge tone={advisor.status === "active" ? "success" : "neutral"}>{ADVISOR_STATUS_LABELS[advisor.status]}</Badge>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Advisor Details">
          <InfoRow label="Advisor code" value={advisor.advisor_code} />
          <InfoRow label="Mobile" value={advisor.mobile} />
          <InfoRow label="Email" value={advisor.email} />
          <InfoRow label="Type" value={ADVISOR_CHANNEL_LABELS[advisor.channel]} />
          <InfoRow
            label="Profession"
            value={advisor.profession ? professionLabel(advisor.profession, advisor.other_profession) : null}
          />
          <InfoRow label="Agency code" value={advisor.agency_code} />
          <InfoRow label="Agent code" value={advisor.agent_code} />
          <PasswordInfoRow hasPassword={advisor.has_password} />
          <InfoRow label="Status" value={ADVISOR_STATUS_LABELS[advisor.status]} />
          <InfoRow label="No. of Policies" value={advisor.no_of_policies} />
          <InfoRow label="Premium Amount" value={formatINR(advisor.total_premium)} />
          {canEdit && (
            <Button variant="secondary" size="sm" className="mt-2" onClick={() => setModal("edit")}>
              Edit
            </Button>
          )}
        </Panel>

        {advisor.recruitment ? (
          <>
            <PersonalInfoPanel lead={advisor.recruitment} />
            <DocumentCollectionPanel lead={advisor.recruitment} />
            <ExaminationHistoryPanel lead={advisor.recruitment} />
          </>
        ) : (
          <Panel title="Recruitment / Application">
            <p className="text-sm text-textSecondary">The linked recruitment lead is no longer available.</p>
          </Panel>
        )}

        <Panel title="Existing Business" className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm text-textSecondary">
              {advisor.no_of_policies} {advisor.no_of_policies === 1 ? "policy" : "policies"} · total premium{" "}
              {formatINR(advisor.total_premium)}
            </p>
            {canEdit && (
              <Button size="sm" onClick={() => setModal("add")}>
                + Add
              </Button>
            )}
          </div>

          {advisor.businesses.length === 0 ? (
            <p className="text-sm text-textSecondary">No business records yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHead>
                  <TableHeadRow>
                    <Th>Customer Name</Th>
                    <Th>Customer Mobile</Th>
                    <Th>Policy Number</Th>
                    <Th>Product Category</Th>
                    <Th>Product Name</Th>
                    <Th>Premium</Th>
                    <Th>PPT</Th>
                    <Th>PT</Th>
                    <Th>Policy Issue Date</Th>
                    <Th>Comment</Th>
                  </TableHeadRow>
                </TableHead>
                <TableBody>
                  {advisor.businesses.map((b) => (
                    <TableRow key={b.id}>
                      <Td>{b.customer_name ?? "—"}</Td>
                      <Td>{b.customer_mobile ?? "—"}</Td>
                      <Td>{b.policy_number ?? "—"}</Td>
                      <Td>{businessCategoryLabel(b.product_category, b.custom_category)}</Td>
                      <Td className="font-medium text-text">{b.product_name}</Td>
                      <Td>{formatINR(b.premium)}</Td>
                      <Td>{b.ppt}</Td>
                      <Td>{b.pt}</Td>
                      <Td>{formatISTDate(b.policy_issue_date)}</Td>
                      <Td className="max-w-[16rem] truncate text-textSecondary">{b.comment ?? "—"}</Td>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </Panel>
      </div>

      {modal === "add" && <AddBusinessModal advisorId={advisor.id} onClose={() => setModal(null)} onSaved={load} />}
      {modal === "edit" && <EditAdvisorModal advisor={advisor} onClose={() => setModal(null)} onSaved={load} />}
    </div>
  );
}
