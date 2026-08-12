export type LoginTabKey = "internal" | "customer";

const TABS: { key: LoginTabKey; label: string }[] = [
  { key: "internal", label: "Employee / Partner" },
  { key: "customer", label: "Customer" },
];

// Sliding-pill tab switcher — the highlight is one absolutely-positioned div translated by
// tab index, so the transition is a transform (cheap, smooth) rather than a background swap.
export function LoginTabs({ active, onChange }: { active: LoginTabKey; onChange: (tab: LoginTabKey) => void }) {
  const activeIndex = TABS.findIndex((t) => t.key === active);

  return (
    <div role="tablist" aria-label="Login type" className="relative grid grid-cols-2 rounded-xl bg-white/10 p-1">
      <div
        aria-hidden="true"
        className="absolute inset-y-1 left-1 w-[calc(50%-4px)] rounded-lg bg-primary shadow-glass transition-transform duration-300 ease-out"
        style={{ transform: `translateX(${activeIndex * 100}%)` }}
      />
      {TABS.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={active === tab.key}
          onClick={() => onChange(tab.key)}
          className={`relative z-10 rounded-lg py-2.5 text-sm font-semibold transition-colors ${
            active === tab.key ? "text-white" : "text-white/60 hover:text-white/80"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
