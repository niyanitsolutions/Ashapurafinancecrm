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
  activeOnly,
}: {
  label: string;
  value: string;
  onChange: (employeeId: string) => void;
  placeholder?: string;
  required?: boolean;
  // Excludes inactive/deactivated employees. Default off (unfiltered) to keep every
  // existing call site byte-for-byte unchanged — opt in where the business rule actually
  // requires it (e.g. Geo Exceptions).
  activeOnly?: boolean;
}) {
  const [options, setOptions] = useState<{ value: string; label: string }[] | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    setOptions(null);
    setLoadError(false);
    // page_size is capped at this app's MAX_PAGE_SIZE (100, see app/constants/api.py) —
    // a higher value 422s and was silently swallowed by the .catch below, which is why
    // this dropdown used to render empty.
    listEmployees({ page: 1, page_size: 100, status: activeOnly ? "active" : undefined })
      .then((res) =>
        setOptions(
          res.data
            .map((e) => ({ value: e.id, label: e.display_name }))
            .sort((a, b) => a.label.localeCompare(b.label)),
        ),
      )
      .catch(() => setLoadError(true));
  }, [activeOnly]);

  const isLoading = options === null && !loadError;
  const isEmpty = options !== null && options.length === 0;

  return (
    <SelectField
      label={label}
      placeholder={loadError ? "Failed to load employees" : isLoading ? "Loading employees…" : isEmpty ? "No employees found" : placeholder}
      options={options ?? []}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      required={required}
      disabled={loadError || isLoading || isEmpty}
    />
  );
}
