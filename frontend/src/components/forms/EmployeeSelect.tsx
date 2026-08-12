import { useEffect, useState } from "react";
import { SelectField } from "@/components/forms/SelectField";
import { listEmployees } from "@/features/employee/api";

// Shared "pick an employee" dropdown — shows names (display_name), submits the employee's
// id underneath, same as every other <select> in the app. Replaces the raw "Employee ID"
// text inputs previously scattered across Assign Lead/Loan/Insurance Case, Temporary
// Access, Geo Exceptions, and Assign Role.
export function EmployeeSelect({
  label,
  value,
  onChange,
  placeholder = "Select employee",
  required,
}: {
  label: string;
  value: string;
  onChange: (employeeId: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  const [options, setOptions] = useState<{ value: string; label: string }[]>([]);

  useEffect(() => {
    listEmployees({ page: 1, page_size: 200 })
      .then((res) =>
        setOptions(
          res.data
            .map((e) => ({ value: e.id, label: e.display_name }))
            .sort((a, b) => a.label.localeCompare(b.label)),
        ),
      )
      .catch(() => setOptions([]));
  }, []);

  return (
    <SelectField
      label={label}
      placeholder={placeholder}
      options={options}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      required={required}
    />
  );
}
