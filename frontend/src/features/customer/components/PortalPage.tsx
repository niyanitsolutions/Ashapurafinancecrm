import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export function PortalPage({ title, subtitle, backTo, backLabel, actions, children }: {
  title: string; subtitle?: string; backTo?: string; backLabel?: string;
  actions?: ReactNode; children: ReactNode;
}) {
  return <section className="portal-page">
    <header className="portal-page-heading">
      <div>{backTo && <Link className="portal-back" to={backTo}>{backLabel ?? "Back to overview"}</Link>}
        <h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>
      {actions && <div className="portal-page-actions">{actions}</div>}
    </header>
    <div className="portal-page-body">{children}</div>
  </section>;
}

export function PortalProgress({ value, label = "Application progress" }: { value: number; label?: string }) {
  const progress = Math.min(100, Math.max(0, value));
  return <div className="portal-progress"><div><span>{label}</span><strong>{progress}%</strong></div>
    <progress aria-label={label} value={progress} max={100} />
  </div>;
}
