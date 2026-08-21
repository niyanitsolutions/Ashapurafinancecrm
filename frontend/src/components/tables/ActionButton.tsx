import { Link } from "react-router-dom";
import { Icon, type IconName } from "@/theme/icons";

type ActionVariant = "view" | "edit" | "link" | "followup" | "update" | "reject";

// "link" (Generate Link) uses Tailwind's stock indigo scale directly rather than a shared
// theme token — it's a one-off accent for a single row action, not a reusable brand color,
// so it doesn't warrant a new slot in theme/colors.ts.
// "followup"/"update"/"reject" back the Leads workflow redesign's Fresh/My Leads row
// actions (decision 125) — distinct tones so Follow Up/Update/Reject read as different
// actions from Edit at a glance, reusing the same tone tokens Badge/StatusBadge already use.
const VARIANT_CLASSES: Record<ActionVariant, string> = {
  view: "text-info border-info/25 hover:bg-info/10",
  edit: "text-primary border-primary/25 hover:bg-primary/10",
  link: "text-indigo-600 border-indigo-200 hover:bg-indigo-50",
  followup: "text-info border-info/25 hover:bg-info/10",
  update: "text-success border-success/25 hover:bg-success/10",
  reject: "text-danger border-danger/25 hover:bg-danger/10",
};

const VARIANT_ICON: Record<ActionVariant, IconName> = {
  view: "eye",
  edit: "edit",
  link: "link",
  followup: "clock",
  update: "trending-up",
  reject: "x-circle",
};

const VARIANT_LABEL: Record<ActionVariant, string> = {
  view: "View",
  edit: "Edit",
  link: "Generate Link",
  followup: "Follow Up",
  update: "Update",
  reject: "Reject",
};

// Rounded-pill row action button (table Actions column) — white background, tone-colored
// icon + label + light border, tone-tinted hover. Reusable by any list page's Actions
// column, not just Leads. `state` rides along on a `to` navigation (e.g. so Edit can tell
// the destination page to open already in edit mode) — same React Router `Link` prop, not
// a new mechanism.
export function ActionButton({
  to,
  state,
  variant,
  onClick,
}: {
  to?: string;
  state?: unknown;
  variant: ActionVariant;
  onClick?: () => void;
}) {
  const className = `inline-flex h-[34px] items-center gap-1.5 rounded-full border bg-card px-3 text-xs font-semibold transition-colors shadow-sm hover:shadow ${VARIANT_CLASSES[variant]}`;
  const content = (
    <>
      <Icon name={VARIANT_ICON[variant]} className="h-3.5 w-3.5" />
      {VARIANT_LABEL[variant]}
    </>
  );
  if (to) {
    return (
      <Link to={to} state={state} className={className}>
        {content}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} className={className}>
      {content}
    </button>
  );
}
