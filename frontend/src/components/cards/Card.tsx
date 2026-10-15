import type { HTMLAttributes, ReactNode } from "react";

// Shared 20px-radius / soft-shadow card shell for the Dashboard redesign — every KPI,
// chart, table, and mini-card wraps this instead of hand-rolling `bg-card border ...`.
export function Card({ className = "", children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`min-w-0 bg-card border border-border rounded-[12px] shadow-card p-4 sm:p-5 ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  icon,
  action,
}: {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 mb-5">
      <div className="flex items-center gap-2.5 min-w-0">
        {icon}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-text break-words">{title}</h3>
          {subtitle && <p className="text-2xs text-textSecondary break-words">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}
