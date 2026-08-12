import { isFieldVisible } from "@/components/forms/fieldValidation";
import { DynamicFormField } from "@/features/customer/components/DynamicFormField";
import type { FormField, RepeatableGroup } from "@/features/customer/api";

// The single shared field renderer for the Product Schema Engine — Employee Create
// Lead, Referral Partner Add Lead, and the Customer Application flow all render a
// product's Basic Information fields through this one component, grouped by
// `field.section` exactly as the Owner authored them. No portal keeps its own copy of
// the field list or its own rendering logic.

/** Groups an array of `{ section }`-shaped items by section, preserving first-occurrence
 * order — reused for both fields (here) and required documents (see ApplicationPage). */
export function groupBySection<T extends { section: string | null }>(items: T[]): [string | null, T[]][] {
  const order: (string | null)[] = [];
  const groups = new Map<string | null, T[]>();
  for (const item of items) {
    const key = item.section;
    if (!groups.has(key)) {
      groups.set(key, []);
      order.push(key);
    }
    groups.get(key)!.push(item);
  }
  return order.map((key) => [key, groups.get(key)!]);
}

export function ProductSchemaForm({
  fields,
  values,
  onChange,
  disabled = false,
  errors,
}: {
  fields: FormField[];
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  disabled?: boolean;
  errors?: Record<string, string>;
}) {
  // Phase 3.1 — conditional visibility: a field with `visible_when` only renders (and
  // only ever counts toward validation/progress) once its controlling field's value
  // matches. Comes entirely from the schema, never a hardcoded per-product check.
  // Governance round — `hidden` (Owner-set, see SchemaEditorPage) is the same kind of
  // exclusion: never rendered, never validated, never counted toward progress.
  const visibleFields = fields.filter((field) => !field.hidden && isFieldVisible(field, values));
  const sections = groupBySection(visibleFields);
  const noop = () => undefined;

  return (
    <>
      {sections.map(([sectionName, sectionFields]) => (
        <div key={sectionName ?? "_default"} className="mb-6 last:mb-0">
          {sectionName && <h3 className="text-sm font-semibold text-text/70 mb-3">{sectionName}</h3>}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6">
            {sectionFields.map((field) => (
              <DynamicFormField
                key={field.key}
                field={field}
                value={values[field.key]}
                onChange={disabled ? noop : onChange}
                error={errors?.[field.key]}
              />
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

// Phase 3.1 — repeatable sections (Co-Applicants, Partners, Nominees, Directors,
// References, ...). Engine capability only this round: no seeded product declares a
// `repeatable_groups` entry yet (see Phase 3.1 report), but any schema that does gets
// add/remove blocks for free, no component change needed. Each block is its own
// `Record<string, unknown>`; the group's overall value is `Record<string, unknown>[]`.
export function RepeatableGroupsForm({
  groups,
  values,
  onChange,
  disabled = false,
}: {
  groups: RepeatableGroup[];
  values: Record<string, unknown>;
  onChange: (groupKey: string, blocks: Record<string, unknown>[]) => void;
  disabled?: boolean;
}) {
  if (groups.length === 0) return null;

  return (
    <>
      {groups.map((group) => {
        const blocks = (values[group.key] as Record<string, unknown>[] | undefined) ?? [];
        const canAddMore = !disabled && (group.max_count == null || blocks.length < group.max_count);
        const canRemove = !disabled && blocks.length > group.min_count;

        return (
          <div key={group.key} className="mb-6 last:mb-0">
            <h3 className="text-sm font-semibold text-text/70 mb-3">{group.label}</h3>
            {blocks.map((block, index) => (
              <div key={index} className="mb-3 rounded border border-border p-4">
                <ProductSchemaForm
                  fields={group.fields}
                  values={block}
                  disabled={disabled}
                  onChange={(key, value) => {
                    const updated = blocks.map((b, i) => (i === index ? { ...b, [key]: value } : b));
                    onChange(group.key, updated);
                  }}
                />
                {canRemove && (
                  <button
                    type="button"
                    onClick={() => onChange(group.key, blocks.filter((_, i) => i !== index))}
                    className="text-xs text-danger hover:underline"
                  >
                    Remove
                  </button>
                )}
              </div>
            ))}
            {canAddMore && (
              <button type="button" onClick={() => onChange(group.key, [...blocks, {}])} className="text-sm text-primary hover:underline">
                {group.add_button_label ?? `+ Add ${group.label}`}
              </button>
            )}
          </div>
        );
      })}
    </>
  );
}
