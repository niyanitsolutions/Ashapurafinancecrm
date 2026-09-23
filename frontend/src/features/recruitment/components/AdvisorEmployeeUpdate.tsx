import { useContext, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { AuthContext } from "@/features/auth/authContext";
import { listEmployees } from "@/features/employee/api";
import { getErrorMessage } from "@/shared/api/errors";

/** Uses the same mobile match as the Advisor API's is_employee flag. */
export function AdvisorEmployeeUpdate({ mobile, isEmployee }: { mobile: string; isEmployee: boolean }) {
  const auth = useContext(AuthContext);
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (auth?.role !== "owner" || !isEmployee) return null;
  const open = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await listEmployees({ search: mobile, page_size: 100 });
      const employee = result.data.find((e) => e.mobile === mobile);
      if (employee) navigate(`/employees/${employee.id}/edit`);
      else setError("Employee record is no longer available.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return <span><Button size="sm" variant="secondary" loading={busy} onClick={open}>Update Employee</Button>{error && <span role="alert" className="text-xs text-danger">{error}</span>}</span>;
}
