import type { HTMLAttributes, ReactNode, TableHTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";

// Shared presentational table pieces — rounded container, sticky header, alternating
// row tint, hover highlight — so every hand-rolled `<table>` across the app (Leads,
// Customers, Applications, Loan/Insurance cases, ...) gets the same enterprise look by
// swapping tag names, without forcing a rigid columns/rows data-grid API onto pages whose
// cell content (links, badges, conditional columns) is genuinely bespoke per page.
export function TableContainer({ children }: { children: ReactNode }) {
  return <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">{children}</div>;
}

export function Table({ className = "", ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return <table className={`w-full text-sm ${className}`} {...props} />;
}

export function TableHead({ className = "", ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={`sticky top-0 z-10 bg-background/95 backdrop-blur-sm ${className}`} {...props} />;
}

export function TableHeadRow({ className = "", ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={`border-b border-border text-left ${className}`} {...props} />;
}

export function Th({ className = "", ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={`px-4 py-3 text-xs font-semibold uppercase tracking-wide text-textSecondary whitespace-nowrap ${className}`} {...props} />;
}

export function TableBody({ className = "", ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={className} {...props} />;
}

export function TableRow({ className = "", ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={`border-b border-border last:border-0 transition-colors even:bg-background/40 hover:bg-primary/5 ${className}`}
      {...props}
    />
  );
}

export function Td({ className = "", ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={`px-4 py-3.5 ${className}`} {...props} />;
}
