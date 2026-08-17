import { useEffect, useState } from "react";
import { listEmployees } from "@/features/employee/api";

// Shared employee-id -> display_name lookup, for pages that show a raw employee_id in a
// results table alongside an EmployeeSelect above it (e.g. Temporary Access, Geo
// Exceptions) and want to render the name instead.
export function useEmployeeNameMap(): Record<string, string> {
  const [names, setNames] = useState<Record<string, string>>({});

  useEffect(() => {
    // page_size is capped at this app's MAX_PAGE_SIZE (100, see app/constants/api.py).
    listEmployees({ page: 1, page_size: 100 })
      .then((res) => setNames(Object.fromEntries(res.data.map((e) => [e.id, e.display_name]))))
      .catch(() => setNames({}));
  }, []);

  return names;
}
