import { Icon } from "@/theme/icons";

function getPageNumbers(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: (number | "ellipsis")[] = [1];
  if (current > 3) pages.push("ellipsis");
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) pages.push(p);
  if (current < total - 2) pages.push("ellipsis");
  pages.push(total);
  return pages;
}

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

// Shared rounded pagination — page-number pills (current page filled orange), Previous/
// Next, a "Showing X to Y of Z" summary, and an optional rows-per-page dropdown. Built for
// the Leads list redesign but generic enough for any paginated list page.
export function Pagination({
  page,
  totalPages,
  totalItems,
  pageSize,
  itemLabel = "items",
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  totalPages: number;
  totalItems: number;
  pageSize: number;
  itemLabel?: string;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
}) {
  const rangeStart = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, totalItems);

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 mt-4 text-sm text-textSecondary">
      <span>
        Showing {rangeStart} to {rangeEnd} of {totalItems} {itemLabel}
      </span>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            aria-label="Previous page"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-border hover:bg-background transition-colors disabled:opacity-40 disabled:hover:bg-transparent"
          >
            <Icon name="chevron-left" className="h-4 w-4" />
          </button>

          {getPageNumbers(page, totalPages).map((p, i) =>
            p === "ellipsis" ? (
              <span key={`ellipsis-${i}`} className="w-9 text-center text-textSecondary">
                …
              </span>
            ) : (
              <button
                key={p}
                type="button"
                onClick={() => onPageChange(p)}
                aria-current={p === page ? "page" : undefined}
                className={`h-9 w-9 rounded-lg text-sm font-medium transition-colors ${
                  p === page ? "bg-primary text-white" : "border border-border bg-card text-text hover:bg-background"
                }`}
              >
                {p}
              </button>
            ),
          )}

          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
            aria-label="Next page"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-border hover:bg-background transition-colors disabled:opacity-40 disabled:hover:bg-transparent"
          >
            <Icon name="chevron-right" className="h-4 w-4" />
          </button>
        </div>

        {onPageSizeChange && (
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="rounded-lg border border-border bg-card px-2.5 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>
                {size} / page
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}
