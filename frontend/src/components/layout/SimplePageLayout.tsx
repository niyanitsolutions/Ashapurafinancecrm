import type { ReactNode } from "react";
import { Link } from "react-router-dom";

// Per-page chrome, rendered inside AppShell's <Outlet/> (the sidebar/topbar shell lives
// there — this only adds the page's own title/actions header). `subtitle` is optional;
// every existing call site that only passes `title`/`backTo`/`actions` keeps rendering
// exactly as before.
export function SimplePageLayout({
  title,
  subtitle,
  backTo,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  backTo?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background">
      <header className="bg-card border-b border-border px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            {backTo && (
              <Link to={backTo} className="mt-1 text-sm text-text/60 hover:text-primary shrink-0">
                ← Back
              </Link>
            )}
            <div>
              <h1 className="text-xl font-semibold text-text">{title}</h1>
              {subtitle && <p className="mt-1 text-sm text-text/70">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      </header>
      <main className="p-6">{children}</main>
    </div>
  );
}
