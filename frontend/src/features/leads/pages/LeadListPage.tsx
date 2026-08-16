import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
import { ASSIGNED_SENTINEL, UNASSIGNED_SENTINEL, exportLeadsCsvUrl, listLeads, type LeadListItem } from "@/features/leads/api";
import { getErrorMessage } from "@/features/leads/errors";
import { leadSourcesApi, type NamedMasterData } from "@/features/system_settings/api";
import { getAccessToken } from "@/shared/api/client";
import { Icon } from "@/theme/icons";

// Leads (including Meta Lead Ads, which arrive via a server-side webhook the browser
// has no way to be pushed by) must appear without the user pressing refresh. This
// project has no WebSocket/SSE infrastructure anywhere yet (see DashboardPage's own
// `refreshIntervalMs`/`setInterval` widget-refresh for the established precedent) — a
// short poll on the first page is the same "reuse existing architecture" tradeoff,
// scoped to the fastest end of a deliberately-chosen 10-15s range rather than a full new
// realtime transport for a single-tenant, low-volume-webhook CRM.
const POLL_INTERVAL_MS = 15_000;

const ALL_OPTIONAL_COLUMNS: ColumnOption[] = [
  { key: "mobile", label: "Mobile" },
  { key: "source", label: "Source" },
  { key: "product", label: "Product" },
  { key: "assigned_to", label: "Assigned To" },
  { key: "status", label: "Status" },
  { key: "created_at", label: "Created On" },
];

function formatDateTime(iso: string): { date: string; time: string } {
  const d = new Date(iso);
  return {
    date: d.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" }),
    time: d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: true }),
  };
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

export function LeadListPage({ assignedOnly }: { assignedOnly: boolean }) {
  const { can } = usePermissions();
  const canCreate = can("leads:leads", "create");
  const canEdit = can("leads:leads", "edit");
  const canExport = can("leads:leads", "export");
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

  // "assigned_to" always exists in this list (rather than only when `assignedOnly` is
  // true) so it survives a New Leads <-> Assigned Leads tab switch: both tabs render the
  // same <LeadListPage> component type at the same Outlet position, so React re-renders
  // it with a new `assignedOnly` prop rather than remounting it — a `visibleColumns`
  // Set computed only from a lazy useState initializer would otherwise freeze at
  // whichever tab was visited first. Rendering still gates "Assigned To" on
  // `assignedOnly` below, so New Leads never shows it.
  const menuColumns = assignedOnly ? ALL_OPTIONAL_COLUMNS : ALL_OPTIONAL_COLUMNS.filter((c) => c.key !== "assigned_to");
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => new Set(ALL_OPTIONAL_COLUMNS.map((c) => c.key)));
  const toggleColumn = (key: string) =>
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const isVisible = (key: string) => visibleColumns.has(key);
  const columnCount = 3 + menuColumns.filter((c) => isVisible(c.key)).length;

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
      assigned_to: assignedOnly ? ASSIGNED_SENTINEL : UNASSIGNED_SENTINEL,
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

  useEffect(load, [page, pageSize, search, productCategory, sourceId, assignedOnly]);

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
  }, [page, pageSize, search, productCategory, sourceId, assignedOnly]);

  const clearFilters = () => {
    setSearch("");
    setProductCategory("");
    setSourceId("");
    setPage(1);
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

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
                <h1 className="text-lg font-bold text-text">{assignedOnly ? "Assigned Leads" : "New Leads"}</h1>
                <p className="text-sm text-textSecondary mt-0.5">
                  {assignedOnly
                    ? "Leads that have been assigned to an employee."
                    : "Newly captured leads from every source, waiting to be assigned."}
                </p>
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
                  {assignedOnly && isVisible("assigned_to") && <Th>Assigned To</Th>}
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
                      ) : assignedOnly ? (
                        <EmptyState icon="leads" title="No leads assigned yet" description="Assigned leads will appear here once someone assigns a new lead to an employee." />
                      ) : (
                        <EmptyState
                          icon="leads"
                          title="You haven't created any leads yet"
                          description="Create your first lead to begin tracking a prospect through to a loan or insurance application."
                          primaryAction={canCreate ? { label: "Create Lead", to: "/leads/new" } : undefined}
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
                      {assignedOnly && isVisible("assigned_to") && <Td>{lead.assigned_to_name || "—"}</Td>}
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
                          <ActionButton to={`/leads/${lead.id}`} variant="view" />
                          <ActionButton variant="link" onClick={() => setLinkModalLead(lead)} />
                          {canEdit && <ActionButton to={`/leads/${lead.id}`} state={{ startEditing: true }} variant="edit" />}
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
    </div>
  );
}
