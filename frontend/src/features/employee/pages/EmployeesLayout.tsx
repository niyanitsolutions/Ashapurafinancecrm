import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

const TABS = [
  {label:"Employee Directory",to:"/employees",matchKey:"employees",exact:true},
  {label:"Add Employee",to:"/employees/new",matchKey:"employees"},
  {label:"Employee Onboarding",to:"/employees/onboarding",matchKey:"employees"},
  {label:"Employee Documents",to:"/employees/documents",matchKey:"employees"},
  {label:"Employee Attendance",to:"/employees/attendance",matchKey:"employees"},
  {label:"Leave Management",to:"/employees/leave",matchKey:"employees"},
  {label:"Employee Login & Logout",to:"/employees/login-logout",matchKey:"employees"},
  {label:"Employee Edit Requests",to:"/employees/edit-requests",matchKey:"employees"},
  {label:"Employee Activity",to:"/employees/activity",matchKey:"employees"},
  {label:"Employee Reports",to:"/employees/reports",matchKey:"employees"},
  {label:"Employee Settings",to:"/employees/settings",matchKey:"employees"},

];

export function EmployeesLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
