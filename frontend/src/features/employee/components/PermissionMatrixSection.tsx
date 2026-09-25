import { useMemo, useState, type ReactNode } from "react";
import type { Permission } from "@/features/access_control/api";
import { applyActionToggle } from "@/features/access_control/permissionHierarchy";
import { Icon, type IconName } from "@/theme/icons";
import {
  DENY_PREFIX,
  MATRIX_ACTIONS,
  MODULE_DISABLED,
  MODULE_ENABLED,
  PERMISSION_MATRIX_ROWS,
  findRowPermission,
  type MatrixAction,
} from "@/features/employee/permissionMatrix";

const ACTION_COPY: Record<MatrixAction, { title: string; help: string }> = {
  view: { title: "View", help: "Can view" },
  create: { title: "Create", help: "Can add" },
  edit: { title: "Edit", help: "Can modify" },
};

const MODULE_ICONS: Record<string, IconName> = {
  audit: "shield-check",
  communication: "communication",
  customer: "customers",
  employee: "employees",
  employee_management: "employees",
  insurance_management: "insurance",
  integrations: "integrations",
  lead_capture: "lead-capture",
  leads: "leads",
  loan_management: "loan",
  owner: "shield-check",
  recruitment: "employees",
  referral_partner_management: "referral",
  reminders: "tasks",
  reporting: "reports",
  system_settings: "settings",
};

function applyCellChange(next: Record<string, Set<string>>, permission: Permission, action: MatrixAction, isChecked: boolean): void {
  next[permission.id] = applyActionToggle(next[permission.id] ?? new Set(), action, isChecked, permission.actions);
}

function PermissionCheckbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <label role="cell" className="flex min-h-12 w-full cursor-pointer items-center justify-center rounded-lg transition-colors hover:bg-primary/5 focus-within:ring-2 focus-within:ring-primary/30">
      <input
        type="checkbox"
        aria-label={label}
        checked={checked}
        onChange={onChange}
        className="h-[22px] w-[22px] cursor-pointer rounded-md border-2 border-border accent-primary focus-visible:outline-none"
      />
    </label>
  );
}

function ActionHeader() {
  return (
    <div role="row" className="sticky top-0 z-10 grid grid-cols-[minmax(16rem,1fr)_repeat(3,6.5rem)] border-b border-border bg-card/95 px-4 py-3 shadow-sm backdrop-blur">
      <span role="columnheader" className="self-center text-xs font-semibold uppercase tracking-wide text-textSecondary">Module / Page</span>
      {MATRIX_ACTIONS.map((action) => <span role="columnheader" key={action} className="text-center"><span className="block text-xs font-semibold uppercase tracking-wide text-text">{ACTION_COPY[action].title}</span><span className="mt-0.5 block text-[10px] font-normal text-text/45">{ACTION_COPY[action].help}</span></span>)}
    </div>
  );
}

export function PermissionMatrixSection({ permissions, checked, onChange }: {
  permissions: Permission[];
  checked: Record<string, Set<string>>;
  onChange: (next: Record<string, Set<string>>) => void;
}) {
  const [query, setQuery] = useState("");
  const hierarchyRoots = useMemo(() => permissions.filter((permission) => permission.node_type === "module"), [permissions]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const permissionByKey = useMemo(() => new Map(permissions.map((permission) => [`${permission.module}:${permission.resource}`, permission])), [permissions]);
  const childrenByParent = useMemo(() => {
    const map = new Map<string, Permission[]>();
    for (const permission of permissions) {
      if (!permission.parent_resource) continue;
      const key = `${permission.module}:${permission.parent_resource}`;
      map.set(key, [...(map.get(key) ?? []), permission]);
    }
    return map;
  }, [permissions]);

  const labelFor = (permission: Permission) => permission.label || permission.resource.replace(/_/g, " ");
  const effective = (permission: Permission, action: MatrixAction): boolean => {
    const selected = checked[permission.id] ?? new Set<string>();
    if (selected.has(action)) return true;
    if (selected.has(`${DENY_PREFIX}${action}`)) return false;
    if (!permission.parent_resource) return false;
    const parent = permissionByKey.get(`${permission.module}:${permission.parent_resource}`);
    return parent ? effective(parent, action) : false;
  };

  const toggleCell = (permission: Permission, action: MatrixAction) => {
    const next = { ...checked };
    const isCurrentlyChecked = (checked[permission.id] ?? new Set()).has(action);
    applyCellChange(next, permission, action, !isCurrentlyChecked);
    if (permission.node_type === "module" && action === "view" && isCurrentlyChecked) {
      for (const child of permissions.filter((candidate) => candidate.module === permission.module && candidate.node_type !== "module")) {
        const childSelection = new Set(next[child.id] ?? []);
        if ((childSelection.has("create") || childSelection.has("edit")) && !childSelection.has("view")) {
          childSelection.delete(`${DENY_PREFIX}view`);
          childSelection.add("view");
          next[child.id] = childSelection;
        }
      }
    }
    if (permission.node_type === "module" && !isCurrentlyChecked) {
      next[permission.id].delete(MODULE_DISABLED);
      next[permission.id].add(MODULE_ENABLED);
    }
    onChange(next);
  };

  const cycleOverride = (permission: Permission, action: MatrixAction) => {
    const next = { ...checked };
    const selected = new Set(checked[permission.id] ?? []);
    const deny = `${DENY_PREFIX}${action}`;
    if (selected.has(action)) { selected.delete(action); selected.add(deny); }
    else if (selected.has(deny)) selected.delete(deny);
    else {
      selected.add(action);
      if (action === "create" || action === "edit") {
        selected.delete(`${DENY_PREFIX}view`);
        if (!effective(permission, "view")) selected.add("view");
      }
    }
    if (action === "view" && selected.has(deny)) {
      for (const dependent of ["create", "edit"] as const) { selected.delete(dependent); selected.add(`${DENY_PREFIX}${dependent}`); }
    }
    next[permission.id] = selected;
    onChange(next);
  };

  const toggleModule = (permission: Permission) => {
    const next = { ...checked };
    const selected = new Set(checked[permission.id] ?? []);
    const enabled = !selected.has(MODULE_ENABLED);
    selected.delete(MODULE_ENABLED); selected.delete(MODULE_DISABLED);
    selected.add(enabled ? MODULE_ENABLED : MODULE_DISABLED);
    next[permission.id] = selected;
    onChange(next);
  };

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const nodeMatches = (permission: Permission): boolean => {
    if (!normalizedQuery) return true;
    if (labelFor(permission).toLocaleLowerCase().includes(normalizedQuery)) return true;
    return (childrenByParent.get(`${permission.module}:${permission.resource}`) ?? []).some(nodeMatches);
  };

  const renderNode = (permission: Permission, depth: number): ReactNode => {
    if (!nodeMatches(permission)) return null;
    const children = childrenByParent.get(`${permission.module}:${permission.resource}`) ?? [];
    const label = labelFor(permission);
    return <div key={permission.id}>
      <div role="row" className="grid grid-cols-[minmax(16rem,1fr)_repeat(3,6.5rem)] items-center border-b border-border/70 px-4 text-sm transition-colors hover:bg-primary/[0.035]">
        <div role="rowheader" className="relative flex min-h-14 items-center gap-3" style={{ paddingLeft: `${Math.min(depth, 3) * 1.25}rem` }}>
          {depth > 0 && <span className="absolute bottom-0 top-0 w-px bg-border/70" style={{ left: `${Math.max(0, depth * 1.25 - 0.65)}rem` }} />}
          <span className={depth > 1 ? "text-text/75" : "font-medium text-text"}>{label}</span>
        </div>
        {MATRIX_ACTIONS.map((action) => permission.actions.includes(action) ? (
          <PermissionCheckbox key={action} label={`${ACTION_COPY[action].help} ${label}`} checked={effective(permission, action)} onChange={() => cycleOverride(permission, action)} />
        ) : <span key={action} aria-label={`${ACTION_COPY[action].title} not available for ${label}`} className="text-center text-lg text-text/20">—</span>)}
      </div>
      {children.map((child) => renderNode(child, depth + 1))}
    </div>;
  };

  const toggleCollapsed = (id: string) => setCollapsed((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  if (hierarchyRoots.length > 0) {
    const visibleRoots = hierarchyRoots.filter(nodeMatches);
    return <section className="overflow-hidden rounded-card border border-border bg-card shadow-card" aria-labelledby="permissions-heading">
      <div className="flex flex-col gap-4 border-b border-border p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6">
        <div><h2 id="permissions-heading" className="text-base font-semibold text-text">Permissions</h2><p className="mt-1 max-w-2xl text-sm text-text/55">Choose what this employee can access and what actions they can perform.</p><p className="mt-1 text-xs text-text/40">View allows access. Create allows adding new records. Edit allows modifying existing records.</p></div>
        <label className="relative block w-full sm:w-72"><span className="sr-only">Search permissions</span><Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text/40" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search permissions..." className="w-full rounded-xl border border-border bg-background py-2.5 pl-9 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/25" /></label>
      </div>
      <div className="max-h-[36rem] overflow-auto">
        <div role="table" aria-label="Permission matrix" className="min-w-[44rem]"><ActionHeader />
          {permissions.length === 0 && <p className="p-6 text-sm text-text/40">Loading...</p>}
          {visibleRoots.length === 0 && permissions.length > 0 && <p className="p-8 text-center text-sm text-text/45">No permissions match your search.</p>}
          {visibleRoots.map((root) => {
            const selected = checked[root.id] ?? new Set<string>();
            const label = labelFor(root);
            const isCollapsed = collapsed.has(root.id) && !normalizedQuery;
            return <div key={root.id} className="border-b-4 border-background last:border-b-0">
              <div role="row" className="grid grid-cols-[minmax(16rem,1fr)_repeat(3,6.5rem)] items-center bg-primary/[0.055] px-4">
                <div role="rowheader" className="flex min-h-[4.25rem] items-center gap-2">
                  <button type="button" aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${label}`} aria-expanded={!isCollapsed} onClick={() => toggleCollapsed(root.id)} className="flex min-w-0 flex-1 items-center gap-3 rounded-lg py-2 text-left hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-text/55"><Icon name={isCollapsed ? "chevron-right" : "chevron-down"} className="h-4 w-4" /></span>
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon name={MODULE_ICONS[root.module] ?? "grid"} className="h-[18px] w-[18px]" /></span>
                    <span className="truncate font-semibold text-text">{label}</span>
                  </button>
                  <label title={`Enable ${label} access`} className="flex cursor-pointer items-center rounded-lg p-2 focus-within:ring-2 focus-within:ring-primary/30"><input type="checkbox" aria-label={`Enable ${label}`} checked={selected.has(MODULE_ENABLED)} onChange={() => toggleModule(root)} className="h-[22px] w-[22px] rounded-md border-2 border-border accent-primary" /></label>
                </div>
                {MATRIX_ACTIONS.map((action) => root.actions.includes(action) ? <PermissionCheckbox key={action} label={`${ACTION_COPY[action].help} ${label}`} checked={selected.has(action)} onChange={() => toggleCell(root, action)} /> : <span key={action} aria-label={`${ACTION_COPY[action].title} not available for ${label}`} className="text-center text-lg text-text/20">—</span>)}
              </div>
              {!isCollapsed && (childrenByParent.get(`${root.module}:${root.resource}`) ?? []).map((child) => renderNode(child, 1))}
            </div>;
          })}
        </div>
      </div>
    </section>;
  }

  const toggleColumn = (action: MatrixAction) => {
    const applicable = PERMISSION_MATRIX_ROWS.map((row) => findRowPermission(permissions, row)).filter((p): p is Permission => !!p && p.actions.includes(action));
    if (applicable.length === 0) return;
    const allChecked = applicable.every((permission) => (checked[permission.id] ?? new Set()).has(action));
    const next = { ...checked };
    for (const permission of applicable) applyCellChange(next, permission, action, !allChecked);
    onChange(next);
  };
  const visibleRows = PERMISSION_MATRIX_ROWS.filter((row) => !normalizedQuery || row.label.toLocaleLowerCase().includes(normalizedQuery));
  return <section className="overflow-hidden rounded-card border border-border bg-card shadow-card" aria-labelledby="permissions-heading">
    <div className="flex flex-col gap-4 border-b border-border p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6"><div><h2 id="permissions-heading" className="text-base font-semibold">Permissions</h2><p className="mt-1 text-sm text-text/55">Choose what this employee can access and what actions they can perform.</p></div><label className="relative block w-full sm:w-72"><span className="sr-only">Search permissions</span><Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text/40" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search permissions..." className="w-full rounded-xl border border-border bg-background py-2.5 pl-9 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/25" /></label></div>
    <div className="max-h-[36rem] overflow-auto"><div className="min-w-[44rem]"><div className="sticky top-0 z-10 grid grid-cols-[minmax(16rem,1fr)_repeat(3,6.5rem)] border-b border-border bg-card px-4 py-3"><span className="text-xs font-semibold uppercase tracking-wide text-textSecondary">Module / Page</span>{MATRIX_ACTIONS.map((action) => <button key={action} type="button" onClick={() => toggleColumn(action)} className="rounded-lg text-center hover:bg-primary/5"><span className="block text-xs font-semibold uppercase tracking-wide">{ACTION_COPY[action].title}</span><span className="block text-[10px] font-normal text-primary">Select all</span></button>)}</div>{visibleRows.map((row) => { const permission = findRowPermission(permissions, row); return <div key={`${row.module}:${row.resource}`} className="grid grid-cols-[minmax(16rem,1fr)_repeat(3,6.5rem)] items-center border-b border-border/70 px-4 hover:bg-primary/[0.035]"><div className="flex min-h-14 items-center gap-3 font-medium"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon name={MODULE_ICONS[row.module] ?? "grid"} className="h-4 w-4" /></span>{row.label}</div>{MATRIX_ACTIONS.map((action) => permission?.actions.includes(action) ? <PermissionCheckbox key={action} label={`${ACTION_COPY[action].help} ${row.label}`} checked={(checked[permission.id] ?? new Set()).has(action)} onChange={() => toggleCell(permission, action)} /> : <span key={action} className="text-center text-lg text-text/20">—</span>)}</div>; })}</div></div>
  </section>;
}
