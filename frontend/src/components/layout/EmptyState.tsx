import { Link } from "react-router-dom";
import { Icon, type IconName } from "@/theme/icons";

interface EmptyStateAction {
  label: string;
  to?: string;
  onClick?: () => void;
}

// Drop-in replacement for a bare "No X found." row/message — used both standalone and
// nested inside a table's <td colSpan={n}> (kept free of its own card/border wrapper so
// it doesn't double up with the table's own border in that context).
export function EmptyState({
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
}: {
  icon: IconName;
  title: string;
  description?: string;
  primaryAction?: EmptyStateAction;
  secondaryAction?: EmptyStateAction;
}) {
  const renderAction = (action: EmptyStateAction, variant: "primary" | "secondary") => {
    const className =
      variant === "primary"
        ? "hover-lift rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-2.5 px-5 shadow-card"
        : "rounded-xl border border-border text-sm font-medium py-2.5 px-5 text-text/70 hover:bg-background transition-colors";
    if (action.to) {
      return (
        <Link key={action.label} to={action.to} className={className}>
          {action.label}
        </Link>
      );
    }
    return (
      <button key={action.label} type="button" onClick={action.onClick} className={className}>
        {action.label}
      </button>
    );
  };

  return (
    <div className="flex flex-col items-center justify-center text-center py-14 px-6 animate-fade-in">
      <div className="w-16 h-16 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-4">
        <Icon name={icon} className="h-8 w-8" />
      </div>
      <h3 className="text-lg font-semibold text-text mb-1.5">{title}</h3>
      {description && <p className="text-sm text-text/50 max-w-sm mb-6">{description}</p>}
      {(primaryAction || secondaryAction) && (
        <div className="flex items-center gap-3">
          {primaryAction && renderAction(primaryAction, "primary")}
          {secondaryAction && renderAction(secondaryAction, "secondary")}
        </div>
      )}
    </div>
  );
}
