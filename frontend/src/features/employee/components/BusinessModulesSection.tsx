import type { Permission } from "@/features/access_control/api";
import { BUSINESS_MODULES, capabilityOptions, findModulePermission } from "@/features/employee/businessModules";

// Shared by CreateEmployeePage and EditEmployeePage — a controlled component, all state
// (which modules are checked, which optional capabilities under each) lives in the
// parent page so Create can start empty and Edit can pre-populate from the employee's
// existing access. Never mentions "Role"/"Permission"/"Grant"/"Resource"/"Action" — only
// "Business Modules" and plain-English capabilities (see businessModules.ts).
export function BusinessModulesSection({
  permissions,
  selectedModules,
  onToggleModule,
  capabilities,
  onToggleCapability,
}: {
  permissions: Permission[];
  selectedModules: Set<string>;
  onToggleModule: (key: string) => void;
  capabilities: Record<string, Set<string>>;
  onToggleCapability: (permissionId: string, action: string) => void;
}) {
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-6">
      <h2 className="text-sm font-semibold text-text mb-1">Business Modules</h2>
      <p className="text-xs text-text/50 mb-4">
        Which business area does this employee work in? Menus, dashboards, and access to their own records are set up
        automatically.
      </p>
      {permissions.length === 0 && <p className="text-sm text-text/40">Loading…</p>}
      <div className="space-y-4">
        {BUSINESS_MODULES.map((module) => {
          const permission = findModulePermission(permissions, module);
          const isChecked = selectedModules.has(module.key);
          const options = permission ? capabilityOptions(permission) : [];
          return (
            <div key={module.key} className="border border-border rounded-lg p-4">
              <label className="flex items-start gap-2 cursor-pointer">
                <input type="checkbox" className="mt-0.5" checked={isChecked} onChange={() => onToggleModule(module.key)} />
                <span>
                  <span className="text-sm font-medium text-text">{module.label}</span>
                  <span className="block text-xs text-text/50 mt-0.5">Includes: {module.description}</span>
                </span>
              </label>
              {isChecked && permission && options.length > 0 && (
                <div className="mt-3 ml-6">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-text/40 mb-2">Optional Capabilities</h4>
                  <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                    {options.map(({ action, label }) => (
                      <label key={action} className="flex items-center gap-1.5 text-xs text-text/70">
                        <input
                          type="checkbox"
                          checked={(capabilities[permission.id] ?? new Set()).has(action)}
                          onChange={() => onToggleCapability(permission.id, action)}
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
