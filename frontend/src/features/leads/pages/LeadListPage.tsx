import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { ActionButton } from "@/components/tables/ActionButton";
import { Badge, StatusBadge } from "@/components/badges/Badge";
import { Button, BUTTON_BASE_CLASSES, BUTTON_SIZE_CLASSES, BUTTON_VARIANT_CLASSES } from "@/components/buttons/Button";
import { ColumnsMenu, type ColumnOption } from "@/components/tables/ColumnsMenu";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import { usePermissions } from "@/features/access_control/usePermissions";
import { GenerateLinkModal } from "@/features/leads/components/GenerateLinkModal";
import { FollowUpModal } from "@/features/leads/components/FollowUpModal";
import { UpdateStageModal } from "@/features/leads/components/UpdateStageModal";
import {
  ASSIGNED_SENTINEL,
  SELF_SENTINEL,
  UNASSIGNED_SENTINEL,
  exportLeadsCsvUrl,
  listLeads,
  type LeadListItem,
} from "@/features/leads/api";
import { getErrorMessage } from "@/features/leads/errors";
import { leadSourcesApi, type NamedMasterData } from "@/features/system_settings/api";
import { getAccessToken } from "@/shared/api/client";
import { formatISTDate, formatISTTime, istDateKey, todayISTDateString } from "@/shared/dateFormat";
import { Icon } from "@/theme/icons";

// Leads (including Meta Lead Ads, which arrive via a server-side webhook the browser
// has no way to be pushed by) must appear without the user pressing refresh. This
// project has no WebSocket/SSE infrastructure anywhere yet (see DashboardPage's own
// `refreshIntervalMs`/`setInterval` widget-refresh for the established precedent) — a
// short poll on the first page is the same "reuse existing architecture" tradeoff,
// scoped to the fastest end of a deliberately-chosen 10-15s range rather than a full new
// realtime transport for a single-tenant, low-volume-webhook CRM.
const POLL_INTERVAL_MS = 15_000;

export type LeadTab = "fresh" | "my" | "document_collection" | "rejected" | "assigned";

// Query params per tab (decision 125) — mirrors the exact scoping
// `LeadService._scope_query`/`get_tab_counts` use, so a tab's list and its own count
// badge can never disagree. See backend/app/features/leads/service.py.
const TAB_QUERY: Record<LeadTab, { assigned_to?: string; stage?: string; exclude_stage?: string }> = {
  fresh: { assigned_to: UNASSIGNED_SENTINEL, stage: "fresh" },
  my: { assigned_to: SELF_SENTINEL, stage: "assigned" },
  document_collection: { stage: "document_collection" },
  rejected: { stage: "rejected" },
  assigned: { assigned_to: ASSIGNED_SENTINEL, exclude_stage: "rejected" },
};

const TAB_META: Record<LeadTab, { title: string; description: string; emptyTitle: string; emptyDescription: string }> = {
  fresh: {
    title: "Fresh Leads",
    description: "Newly captured leads from every source, waiting to be assigned.",
    emptyTitle: "You haven't created any leads yet",
    emptyDescription: "Create your first lead to begin tracking a prospect through to a loan or insurance application.",
  },
  my: {
    title: "My Leads",
    description: "Leads currently assigned to you.",
    emptyTitle: "No leads assigned to you yet",
    emptyDescription: "Leads assigned to you — by yourself or by another team member — will appear here.",
  },
  document_collection: {
    title: "Document Collection",
    description: "Leads currently collecting application documents.",
    emptyTitle: "No leads in Document Collection",
    emptyDescription: "Move a lead here from My Leads once you're ready to start collecting documents.",
  },
  rejected: {
    title: "Rejected",
    description: "Leads that were explicitly rejected, kept for reporting and audit.",
    emptyTitle: "No rejected leads",
    emptyDescription: "Rejected leads will appear here once a lead is rejected from My Leads.",
  },
  assigned: {
    title: "Assigned",
    description: "Every lead currently assigned to an employee.",
    emptyTitle: "No leads assigned yet",
    emptyDescription: "Assigned leads will appear here once someone assigns a new lead to an employee.",
  },
};

const ALL_OPTIONAL_COLUMNS: ColumnOption[] = [
  { key: "mobile", label: "Mobile" },
  { key: "source", label: "Source" },
  { key: "product", label: "Product" },
  { key: "assigned_to", label: "Assigned To" },
  { key: "status", label: "Status" },
  { key: "created_at", label: "Created On" },
];

function formatDateTime(iso: string): { date: string; time: string } {
  return { date: formatISTDate(iso), time: formatISTTime(iso) };
}

// Past = red, Today = blue, Future = green (spec section 5) — computed from the IST
// calendar date only, never the frontend letting a user pick a color, and never a raw
// browser-local comparison (see @/shared/dateFormat's IST discipline).
function followUpTone(iso: string | null): "danger" | "info" | "success" | null {
  if (!iso) return null;
  const day = istDateKey(iso);
  const today = todayISTDateString();
  if (day < today) return "danger";
  if (day === today) return "info";
  return "success";
}

function NextFollowUp({ iso }: { iso: string | null }) {
  const tone = followUpTone(iso);
  if (!iso || !tone) return <span className="text-text/40">—</span>;
  return <Badge tone={tone}>{formatISTDate(iso)}</Badge>;
}

// Plain `<a href>` can't carry the Bearer token (see shared/api/client.ts:getAccessToken)
// — CSV export needs a real authenticated fetch + blob download instead.
async function downloadLeadsCsv(setError: (msg: string | null) => void) {
  setError(null);
  try {
    const token = getAccessToken();
    const response = await fetch(exportLeadsCsvUrl(), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new Error("Export failed");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "leads.csv";
    link.click();
    URL.revokeObjectURL(url);
  } catch {
    setError("Couldn't export leads. Please try again.");
  }
}

export function LeadListPage({ tab }: { tab: LeadTab }) {
  const { can } = usePermissions();
  const canCreate = can("leads:leads", "create");
  const canEdit = can("leads:leads", "edit");
  const canExport = can("leads:leads", "export");
  const { refreshCounts } = useOutletContext<{ refreshCounts: () => void }>();
  const [items, setItems] = useState<LeadListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [search, setSearch] = useState("");
  const [productCategory, setProductCategory] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [sources, setSources] = useState<NamedMasterData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [linkModalLead, setLinkModalLead] = useState<LeadListItem | null>(null);
  const [followUpLead, setFollowUpLead] = useState<LeadListItem | null>(null);
  const [updateStageLead, setUpdateStageLead] = useState<LeadListItem | null>(null);

  const showAssignedTo = tab === "my" || tab === "document_collection" || tab === "assigned";
  const showNextFollowUp = tab === "fresh" || tab === "my" || tab === "assigned";
  const showRejectedColumns = tab === "rejected";
  const showAssignedColumns = tab === "assigned";
  // Phase 3 (decision 127) — Application status (Pending/Submitted), Document
  // Collection only; read-only enrichment from the existing Application entity.
  const showApplicationStatus = tab === "document_collection";

  const menuColumns = showAssignedTo ? ALL_OPTIONAL_COLUMNS : ALL_OPTIONAL_COLUMNS.filter((c) => c.key !== "assigned_to");
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => new Set(ALL_OPTIONAL_COLUMNS.map((c) => c.key)));
  const toggleColumn = (key: string) =>
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const isVisible = (key: string) => visibleColumns.has(key);
  const columnCount =
    3 +
    menuColumns.filter((c) => isVisible(c.key)).length +
    (showNextFollowUp ? 1 : 0) +
    (showRejectedColumns ? 3 : 0) +
    (showAssignedColumns ? 2 : 0) +
    (showApplicationStatus ? 1 : 0);

  useEffect(() => {
    leadSourcesApi
      .list()
      .then((all) => setSources(all.filter((s) => s.status === "active")))
      .catch(() => setSources([]));
  }, []);

  const hasFilters = Boolean(search || productCategory || sourceId);

  const load = (opts: { silent?: boolean } = {}) => {
    if (!opts.silent) setIsLoading(true);
    listLeads({
      page,
      page_size: pageSize,
      search: search || undefined,
      product_category: productCategory || undefined,
      source_id: sourceId || undefined,
      ...TAB_QUERY[tab],
    })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => {
        // A poll tick failing (a momentary network blip) shouldn't blow away an
        // already-visible, still-valid list with an error banner — only the initial,
        // user-visible load surfaces a failure.
        if (!opts.silent) setError(getErrorMessage(err));
      })
      .finally(() => {
        if (!opts.silent) setIsLoading(false);
      });
  };

  useEffect(load, [page, pageSize, search, productCategory, sourceId, tab]);

  // New leads (Meta Lead Ads webhooks land server-side, with nothing to push the
  // browser) must appear without a manual refresh — silently re-fetch the current view
  // in the background. Only polls the first, unfiltered page: a poll tick re-running
  // for whatever page/search/filter the user has open would otherwise yank them back to
  // page 1 results while they're mid-review of an older page.
  useEffect(() => {
    if (page !== 1 || hasFilters) return;
    const interval = window.setInterval(() => load({ silent: true }), POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, search, productCategory, sourceId, tab]);

  const clearFilters = () => {
    setSearch("");
    setProductCategory("");
    setSourceId("");
    setPage(1);
  };

  const refreshAfterAction = () => {
    load({ silent: true });
    refreshCounts();
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const meta = TAB_META[tab];

  return (
    <div className="min-h-screen bg-background">
      <div className="p-6">
        <ErrorBanner message={error} />

        <div className="bg-card border border-border rounded-card shadow-card overflow-hidden">
          <div className="p-6 flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon name="leads" className="h-5 w-5" />
              </span>
              <div>
                <h1 className="text-lg font-bold text-text">{meta.title}</h1>
                <p className="text-sm text-textSecondary mt-0.5">{meta.description}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {canExport && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<Icon name="download" className="h-4 w-4 text-textSecondary" />}
                  onClick={() => downloadLeadsCsv(setError)}
                >
                  Export
                </Button>
              )}
              {canCreate && (
                <Link
                  to="/leads/new"
                  className={`${BUTTON_BASE_CLASSES} ${BUTTON_VARIANT_CLASSES.primary} ${BUTTON_SIZE_CLASSES.sm}`}
                >
                  <Icon name="plus" className="h-4 w-4" />
                  Create Lead
                </Link>
              )}
            </div>
          </div>

          <div className="px-6 pb-6 flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[240px] max-w-sm">
              <Icon name="search" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-textSecondary" />
              <input
                type="text"
                placeholder="Search by name, code, mobile, email…"
                value={search}
                onChange={(e) => {
                  setPage(1);
                  setSearch(e.target.value);
                }}
                className="w-full rounded-xl border border-border pl-9 pr-3.5 py-2.5 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>
            <select
              value={productCategory}
              onChange={(e) => {
                setPage(1);
                setProductCategory(e.target.value);
              }}
              className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            >
              <option value="">All Products</option>
              <option value="loan">Loan</option>
              <option value="insurance">Insurance</option>
            </select>
            <select
              value={sourceId}
              onChange={(e) => {
                setPage(1);
                setSourceId(e.target.value);
              }}
              className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            >
              <option value="">All Sources</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <div className="ml-auto">
              <ColumnsMenu columns={menuColumns} visible={visibleColumns} onToggle={toggleColumn} />
            </div>
          </div>

          <div className="overflow-x-auto">
            <Table>
              <TableHead>
                <TableHeadRow>
                  <Th>Code</Th>
                  <Th>Name</Th>
                  {isVisible("mobile") && <Th>Mobile</Th>}
                  {isVisible("source") && <Th>Source</Th>}
                  {isVisible("product") && <Th>Product</Th>}
                  {showAssignedTo && isVisible("assigned_to") && <Th>Assigned To</Th>}
                  {showAssignedColumns && <Th>Assigned By</Th>}
                  {showAssignedColumns && <Th>Assigned On</Th>}
                  {showRejectedColumns && <Th>Rejected By</Th>}
                  {showRejectedColumns && <Th>Rejected On</Th>}
                  {showRejectedColumns && <Th>Reason</Th>}
                  {showNextFollowUp && <Th>Next Follow Up</Th>}
                  {showApplicationStatus && <Th>Status</Th>}
                  {isVisible("status") && <Th>Status</Th>}
                  {isVisible("created_at") && <Th>Created On</Th>}
                  <Th>Actions</Th>
                </TableHeadRow>
              </TableHead>
              <TableBody>
                {isLoading && (
                  <tr>
                    <Td colSpan={columnCount} className="text-center text-text/50 py-6">
                      Loading…
                    </Td>
                  </tr>
                )}
                {!isLoading && items.length === 0 && (
                  <tr>
                    <td colSpan={columnCount}>
                      {hasFilters ? (
                        <EmptyState
                          icon="search"
                          title="No leads match your filters"
                          description="Try a different search term or clear the filters."
                          secondaryAction={{ label: "Clear filters", onClick: clearFilters }}
                        />
                      ) : (
                        <EmptyState
                          icon="leads"
                          title={meta.emptyTitle}
                          description={meta.emptyDescription}
                          primaryAction={tab === "fresh" && canCreate ? { label: "Create Lead", to: "/leads/new" } : undefined}
                        />
                      )}
                    </td>
                  </tr>
                )}
                {items.map((lead) => {
                  const created = formatDateTime(lead.created_at);
                  return (
                    <TableRow key={lead.id}>
                      <Td className="whitespace-nowrap">
                        <Link to={`/leads/${lead.id}`} className="text-primary font-medium hover:underline">
                          {lead.lead_code}
                        </Link>
                        {lead.is_potential_duplicate && (
                          <span className="ml-2 inline-block rounded-full bg-warning/10 text-warning text-xs px-2 py-0.5">Possible duplicate</span>
                        )}
                      </Td>
                      <Td className="font-semibold text-text">{lead.full_name}</Td>
                      {isVisible("mobile") && (
                        <Td>
                          <span className="inline-flex items-center gap-1.5 text-text">
                            <Icon name="phone" className="h-3.5 w-3.5 text-textSecondary" />
                            {lead.mobile}
                          </span>
                        </Td>
                      )}
                      {isVisible("source") && (
                        <Td>
                          <Badge tone="info">{lead.source_name}</Badge>
                        </Td>
                      )}
                      {isVisible("product") && <Td>{lead.product_name}</Td>}
                      {showAssignedTo && isVisible("assigned_to") && <Td>{lead.assigned_to_name || "—"}</Td>}
                      {showAssignedColumns && <Td>{lead.assigned_by_name || "—"}</Td>}
                      {showAssignedColumns && <Td>{lead.assigned_at ? formatISTDate(lead.assigned_at) : "—"}</Td>}
                      {showRejectedColumns && <Td>{lead.rejected_by_name || "—"}</Td>}
                      {showRejectedColumns && <Td>{lead.rejected_at ? formatISTDate(lead.rejected_at) : "—"}</Td>}
                      {showRejectedColumns && <Td className="max-w-xs truncate" title={lead.rejected_reason ?? undefined}>{lead.rejected_reason || "—"}</Td>}
                      {showNextFollowUp && (
                        <Td>
                          <NextFollowUp iso={lead.next_follow_up_date} />
                        </Td>
                      )}
                      {showApplicationStatus && (
                        <Td>
                          {lead.application_status === "submitted" ? (
                            <StatusBadge status="submitted" label="Submitted" />
                          ) : (
                            <StatusBadge status="pending" label="Pending" />
                          )}
                        </Td>
                      )}
                      {isVisible("status") && (
                        <Td>
                          <StatusBadge status={lead.status} />
                        </Td>
                      )}
                      {isVisible("created_at") && (
                        <Td>
                          <div className="flex items-center gap-1.5 text-text">
                            <Icon name="calendar" className="h-3.5 w-3.5 text-textSecondary shrink-0" />
                            <div>
                              <div>{created.date}</div>
                              <div className="text-2xs text-textSecondary">{created.time}</div>
                            </div>
                          </div>
                        </Td>
                      )}
                      <Td>
                        <div className="flex items-center gap-2">
                          {/* Document Collection's View opens the existing, unmodified
                              staff Application page (spec §20) once one exists — the
                              same real Accept/Reject/Re-upload/version-history flow
                              every other Application entry point already uses (decision
                              127). Falls back to the Lead's own details page when the
                              customer hasn't used Generate Link yet — there's nothing
                              else to show. */}
                          <ActionButton
                            to={tab === "document_collection" && lead.application_id ? `/applications/${lead.application_id}` : `/leads/${lead.id}`}
                            variant="view"
                          />
                          {tab !== "rejected" && <ActionButton variant="link" onClick={() => setLinkModalLead(lead)} />}
                          {(tab === "fresh" || tab === "my") && canEdit && (
                            <ActionButton variant="followup" onClick={() => setFollowUpLead(lead)} />
                          )}
                          {(tab === "my" || tab === "document_collection") && canEdit && (
                            <ActionButton variant="update" onClick={() => setUpdateStageLead(lead)} />
                          )}
                          {canEdit && tab !== "rejected" && <ActionButton to={`/leads/${lead.id}`} state={{ startEditing: true }} variant="edit" />}
                        </div>
                      </Td>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>

        <Pagination
          page={page}
          totalPages={totalPages}
          totalItems={total}
          pageSize={pageSize}
          itemLabel="leads"
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      </div>

      {linkModalLead && (
        <GenerateLinkModal leadId={linkModalLead.id} leadCode={linkModalLead.lead_code} onClose={() => setLinkModalLead(null)} />
      )}
      {followUpLead && (
        <FollowUpModal
          leadId={followUpLead.id}
          leadCode={followUpLead.lead_code}
          currentFollowUpDate={followUpLead.next_follow_up_date}
          onClose={() => {
            setFollowUpLead(null);
            refreshAfterAction();
          }}
          onSaved={refreshAfterAction}
        />
      )}
      {updateStageLead && (
        <UpdateStageModal lead={updateStageLead} onClose={() => setUpdateStageLead(null)} onChanged={refreshAfterAction} />
      )}
    </div>
  );
}
