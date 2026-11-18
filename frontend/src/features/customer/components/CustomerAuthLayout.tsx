import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import "../portal.css";

export function CustomerAuthLayout({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return <main className="customer-auth"><div className="customer-auth-card">
    <Link to="/login" className="portal-brand"><span className="portal-brand-mark">AFS</span>
      <span>Ashapura Financial Services<small>Customer portal</small></span></Link>
    <h1>{title}</h1>{subtitle && <p className="mt-2 text-slate-600">{subtitle}</p>}
    <div className="mt-6">{children}</div>
    <p className="mt-6 border-t pt-4 text-slate-500">Your information stays in your secure customer account.</p>
  </div></main>;
}
