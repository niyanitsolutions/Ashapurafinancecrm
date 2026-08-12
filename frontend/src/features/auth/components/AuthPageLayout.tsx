import type { ReactNode } from "react";
import loginBackground from "@/assets/images/login-bg.jpg";

// Full-screen glassmorphism over a real dark-navy fintech/network background photo (free,
// standard-license Unsplash image — see src/assets/images/ — chosen deliberately over an
// abstract data-network/security look rather than a trading floor or crypto-chart shot).
// Layered gradients on top keep the glass card readable against it at every viewport width.
// `title` is optional: LoginPage renders its own tab-driven heading instead of a static one
// (see LoginPage.tsx) and passes no title, while ForgotPassword/OtpVerification/
// ResetPassword keep using the built-in heading unchanged.
export function AuthPageLayout({ title, subtitle, children }: { title?: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-navy flex items-center justify-center px-4 py-10">
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: `url(${loginBackground})` }}
        aria-hidden="true"
      />
      <div className="absolute inset-0 bg-gradient-to-br from-navy/90 via-navy/85 to-[#1E293B]/90" />
      <div
        className="absolute inset-0 opacity-60"
        style={{ background: "radial-gradient(circle at 15% 20%, rgba(249,115,22,0.16), transparent 45%), radial-gradient(circle at 85% 75%, rgba(37,99,235,0.22), transparent 45%)" }}
      />

      <div className="relative z-10 w-full max-w-md animate-fade-in">
        <div className="text-center mb-8">
          <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-white font-bold text-xl shadow-glass mb-4">
            AFS
          </div>
          <h1 className="text-xl font-bold text-white tracking-tight">AFS Financial CRM</h1>
          <p className="text-sm text-white/60 mt-1">Secure Financial Relationship Platform</p>
        </div>

        <div className="rounded-card border border-white/15 bg-white/10 backdrop-blur-xl shadow-glass p-8 animate-slide-up">
          {title && (
            <>
              <h2 className="text-lg font-semibold text-white">{title}</h2>
              {subtitle && <p className="text-sm text-white/60 mt-1">{subtitle}</p>}
            </>
          )}
          <div className={title ? "mt-6" : ""}>{children}</div>
        </div>

        <p className="text-center text-xs text-white/40 mt-6 tracking-wide">Secure · Fast · Trusted</p>
      </div>
    </div>
  );
}
