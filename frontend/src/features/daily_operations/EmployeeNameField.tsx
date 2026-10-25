import { useId } from "react";
import { FormField } from "@/components/forms/FormField";

export function EmployeeNameField({ value, onChange, options, disabled = false, label = "Employee name" }: {
  value: string; onChange: (name: string) => void; options: { id: string; name: string }[];
  disabled?: boolean; label?: string;
}) {
  const listId = useId();
  return <>
    <FormField label={label} value={value} list={listId} maxLength={200} disabled={disabled}
      placeholder="Choose or type a name" autoComplete="off" onChange={event => onChange(event.target.value)} />
    <datalist id={listId}>{options.map(employee => <option key={employee.id} value={employee.name} />)}</datalist>
  </>;
}
