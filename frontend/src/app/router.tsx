import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ComingSoonPage } from "@/components/layout/ComingSoonPage";
import { HomeRedirect } from "@/app/HomeRedirect";
import { GeoExceptionPage } from "@/features/access_control/pages/GeoExceptionPage";
import { RoleListPage } from "@/features/access_control/pages/RoleListPage";
import { TemporaryAccessPage } from "@/features/access_control/pages/TemporaryAccessPage";
import { RequireAuth, RequireOwner } from "@/features/auth/components/RequireAuth";
import { DashboardPage } from "@/features/dashboard/pages/DashboardPage";
import { ChangePasswordPage } from "@/features/auth/pages/ChangePasswordPage";
import { ForceChangePasswordPage } from "@/features/auth/pages/ForceChangePasswordPage";
import { ForgotPasswordPage } from "@/features/auth/pages/ForgotPasswordPage";
import { LoginPage } from "@/features/auth/pages/LoginPage";
import { OtpVerificationPage } from "@/features/auth/pages/OtpVerificationPage";
import { ResetPasswordPage } from "@/features/auth/pages/ResetPasswordPage";
import { SessionsPage } from "@/features/auth/pages/SessionsPage";
import { CustomerPortalLayout } from "@/features/customer/components/CustomerPortalLayout";
import { RequireCustomer } from "@/features/customer/components/RequireCustomer";
import { ApplicationListPage } from "@/features/customer/pages/ApplicationListPage";
import { ApplicationPage } from "@/features/customer/pages/ApplicationPage";
import { ApplicationTimelinePage } from "@/features/customer/pages/ApplicationTimelinePage";
import { CompleteProfilePage } from "@/features/customer/pages/CompleteProfilePage";
import { CustomerDetailsPage } from "@/features/customer/pages/CustomerDetailsPage";
import { CustomerListPage } from "@/features/customer/pages/CustomerListPage";
import { CustomersLayout } from "@/features/customer/pages/CustomersLayout";
import { DocumentsPage } from "@/features/customer/pages/DocumentsPage";
import { MessagesPage } from "@/features/customer/pages/MessagesPage";
import { PortalHomePage } from "@/features/customer/pages/PortalHomePage";
import { ProductSelectionPage } from "@/features/customer/pages/ProductSelectionPage";
import { ProfilePage } from "@/features/customer/pages/ProfilePage";
import { RegisterPage } from "@/features/customer/pages/RegisterPage";
import { SecureLinkLandingPage } from "@/features/customer/pages/SecureLinkLandingPage";
import { SupportPage } from "@/features/customer/pages/SupportPage";
import { StaffApplicationDetailsPage } from "@/features/customer/pages/StaffApplicationDetailsPage";
import { StaffApplicationListPage } from "@/features/customer/pages/StaffApplicationListPage";
import { CreateEmployeePage } from "@/features/employee/pages/CreateEmployeePage";
import { EmployeeListPage } from "@/features/employee/pages/EmployeeListPage";
import { EmployeeLoginHistoryPage } from "@/features/employee/pages/EmployeeLoginHistoryPage";
import { EmployeeModulePlaceholderPage } from "@/features/employee/pages/EmployeeModulePlaceholderPage";
import { EmployeeProfilePage } from "@/features/employee/pages/EmployeeProfilePage";
import { EmployeesLayout } from "@/features/employee/pages/EmployeesLayout";
import { InsuranceCaseDetailsPage } from "@/features/insurance_management/pages/InsuranceCaseDetailsPage";
import { InsuranceCaseListPage } from "@/features/insurance_management/pages/InsuranceCaseListPage";
import { InsuranceManagementLayout } from "@/features/insurance_management/pages/InsuranceManagementLayout";
import { IntegrationDetailsPage } from "@/features/integrations/pages/IntegrationDetailsPage";
import { IntegrationListPage } from "@/features/integrations/pages/IntegrationListPage";
import { CreateLeadPage } from "@/features/leads/pages/CreateLeadPage";
import { LeadDetailsPage } from "@/features/leads/pages/LeadDetailsPage";
import { LeadListPage } from "@/features/leads/pages/LeadListPage";
import { LeadsLayout } from "@/features/leads/pages/LeadsLayout";
import { LoanCaseDetailsPage } from "@/features/loan_management/pages/LoanCaseDetailsPage";
import { LoanCaseListPage } from "@/features/loan_management/pages/LoanCaseListPage";
import { LoanManagementLayout } from "@/features/loan_management/pages/LoanManagementLayout";
import { RequireReferralPartner } from "@/features/referral_partner_management/components/RequireReferralPartner";
import { ReferralPartnerPortalLayout } from "@/features/referral_partner_management/components/ReferralPartnerPortalLayout";
import { ReferralPartnerCommissionHistoryPage } from "@/features/referral_partner_management/pages/ReferralPartnerCommissionHistoryPage";
import { ReferralPartnerDashboardPage } from "@/features/referral_partner_management/pages/ReferralPartnerDashboardPage";
import { ReferralPartnerLeadsPage } from "@/features/referral_partner_management/pages/ReferralPartnerLeadsPage";
import { CreateAccountPage } from "@/features/owner/pages/CreateAccountPage";
import { RequirePrimaryOwner } from "@/features/owner/components/RequirePrimaryOwner";
import { CreateSecondaryOwnerPage } from "@/features/owner/pages/CreateSecondaryOwnerPage";
import { EditSecondaryOwnerPage } from "@/features/owner/pages/EditSecondaryOwnerPage";
import { OwnerAccountListPage } from "@/features/owner/pages/OwnerAccountListPage";
import { NotificationListPage } from "@/features/reminders/pages/NotificationListPage";
import { DepartmentsPage } from "@/features/system_settings/pages/DepartmentsPage";
import { DesignationsPage } from "@/features/system_settings/pages/DesignationsPage";
import { DocumentTypesPage } from "@/features/system_settings/pages/DocumentTypesPage";
import { InsuranceProductsPage } from "@/features/system_settings/pages/InsuranceProductsPage";
import { LoanProductsPage } from "@/features/system_settings/pages/LoanProductsPage";
import { SettingsHomePage } from "@/features/system_settings/pages/SettingsHomePage";
import { SettingsLayout } from "@/features/system_settings/pages/SettingsLayout";
import { StatusMastersPage } from "@/features/system_settings/pages/StatusMastersPage";

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/forgot-password",
    element: <ForgotPasswordPage />,
  },
  {
    path: "/verify-otp",
    element: <OtpVerificationPage />,
  },
  {
    path: "/reset-password",
    element: <ResetPasswordPage />,
  },
  // Public Module 6B onboarding entry points — see docs/decisions/DECISIONS.md #046-#049.
  {
    path: "/register",
    element: <RegisterPage />,
  },
  // Login page's "Create New Account" — decides Owner first-run vs. Customer registration.
  {
    path: "/create-account",
    element: <CreateAccountPage />,
  },
  {
    path: "/apply/:secureCode",
    element: <SecureLinkLandingPage />,
  },
  {
    element: <RequireAuth />,
    children: [
      // A pure redirect decision (Owner/Employee -> /dashboard, Customer -> /portal,
      // Referral Partner -> /referral-portal) — deliberately renders nothing itself.
      // "/" and AppShell are siblings under this same RequireAuth, so an index route
      // here can only ever replace RequireAuth's own Outlet, never AppShell's — if this
      // route rendered Dashboard content directly (as it originally did), that content
      // would appear as AppShell's sibling instead of its child, silently skipping the
      // Sidebar/Topbar. Routing every role through a real nested path instead avoids
      // that class of bug entirely, and matches how every other page is reached.
      { index: true, element: <HomeRedirect /> },
      // Standalone, no chrome — same placement pattern as HomeRedirect. Reached only
      // when RequireAuth detects must_change_password (see RequireAuth.tsx).
      { path: "/force-change-password", element: <ForceChangePasswordPage /> },
      {
        // Real shell (Module 5) — Sidebar/Topbar wrap every authenticated Owner/Employee
        // route nested below, including /dashboard itself now (see HomeRedirect.tsx).
        element: <AppShell />,
        children: [
          { path: "/dashboard", element: <DashboardPage /> },
          { path: "/profile", element: <EmployeeProfilePage /> },
          { path: "/profile/change-password", element: <ChangePasswordPage /> },
          { path: "/profile/sessions", element: <SessionsPage backTo="/profile" /> },
          { path: "/profile/login-history", element: <EmployeeLoginHistoryPage scope="self" /> },
          // Not RequireOwner-wrapped — Employees granted `leads:leads` (Access Control)
          // reach these too; the backend enforces the real permission, not this route guard.
          {
            // New Leads / Assigned Leads tabs — same list component reused per tab via
            // the `assignedOnly` prop (fixedStatus/reEligible pattern, see Loan/Insurance
            // Management below). Create/detail routes sit outside the tab layout, same
            // precedent as Employees' create/detail routes.
            path: "/leads",
            element: <LeadsLayout />,
            children: [
              { index: true, element: <LeadListPage assignedOnly={false} /> },
              { path: "assigned", element: <LeadListPage assignedOnly /> },
            ],
          },
          { path: "/leads/new", element: <CreateLeadPage /> },
          { path: "/leads/:leadId", element: <LeadDetailsPage /> },
          // Module 6B staff views — role-gated server-side (require_staff / require_owner,
          // decision 050), not permission-based, so no RequireOwner wrapper here either.
          // Secure link generation/management now happens inline on LeadDetailsPage's own
          // card + modal (no separate navigation) — no route needed for it anymore.
          {
            // Customers / Customer Applications tabs — same shared-layout pattern as
            // Employees (list-level tabs share a layout, detail routes sit outside it).
            // /applications isn't nested under /customers in the URL, same as
            // AdministrationLayout already grouping unrelated absolute paths.
            element: <CustomersLayout />,
            children: [
              { path: "/customers", element: <CustomerListPage /> },
              { path: "/applications", element: <StaffApplicationListPage /> },
            ],
          },
          { path: "/customers/:customerId", element: <CustomerDetailsPage /> },
          { path: "/applications/:applicationId", element: <StaffApplicationDetailsPage /> },
          // Module 6C — permission-gated server-side (require_permission("loan_management"/
          // "insurance_management", "applications", ...), not require_owner), so no
          // RequireOwner wrapper here either. Left exactly as-is for back-compat
          // (bookmarks, dashboard widgets, ?status= deep links); the sidebar now points
          // into /loan-management and /insurance-management below instead.
          { path: "/loan-cases", element: <LoanCaseListPage /> },
          { path: "/loan-cases/:caseId", element: <LoanCaseDetailsPage /> },
          { path: "/insurance-cases", element: <InsuranceCaseListPage /> },
          { path: "/insurance-cases/:caseId", element: <InsuranceCaseDetailsPage /> },
          // Tabbed Loan/Insurance Management — same list pages as above, reused verbatim
          // (fixedStatus/reEligible are additive optional props), just addressed under a
          // dedicated URL per tab instead of one page with a ?status= query string.
          {
            path: "/loan-management",
            element: <LoanManagementLayout />,
            children: [
              { index: true, element: <Navigate to="/loan-management/cases" replace /> },
              { path: "cases", element: <LoanCaseListPage /> },
              { path: "disbursements", element: <LoanCaseListPage fixedStatus="disbursed" /> },
              { path: "re-eligible", element: <LoanCaseListPage reEligible /> },
              { path: "rejected", element: <LoanCaseListPage fixedStatus="rejected" /> },
            ],
          },
          {
            path: "/insurance-management",
            element: <InsuranceManagementLayout />,
            children: [
              { index: true, element: <Navigate to="/insurance-management/cases" replace /> },
              { path: "cases", element: <InsuranceCaseListPage /> },
              { path: "policies-issued", element: <InsuranceCaseListPage fixedStatus="policy_issued" /> },
              { path: "re-eligible", element: <InsuranceCaseListPage reEligible /> },
              { path: "rejected", element: <InsuranceCaseListPage fixedStatus="rejected" /> },
            ],
          },
          // Module 6D — Tasks permission-gated server-side (require_permission
          // "reminders"/"tasks"), Notifications self-service (require_staff only, no
          // permission needed — each user reads only their own inbox).
          // Phase 1 deployment scope: Tasks isn't shipping yet — see ComingSoonPage.
          { path: "/tasks", element: <ComingSoonPage title="Tasks" /> },
          { path: "/notifications", element: <NotificationListPage /> },
          // Reminder Rules automates Tasks — out of Phase 1 scope alongside it.
          { path: "/reminder-rules", element: <ComingSoonPage title="Reminder Rules" /> },
          // Module 8 — Phase 1 deployment scope: Reports & Analytics isn't shipping yet.
          {
            element: <ComingSoonPage title="Reports & Analytics" />,
            children: [
              { path: "/reports", element: <ComingSoonPage title="Reports & Analytics" /> },
              { path: "/scheduled-reports", element: <ComingSoonPage title="Reports & Analytics" /> },
            ],
          },
          { path: "/reports/:reportKey", element: <ComingSoonPage title="Reports & Analytics" /> },
          // Module 9A — permission-gated server-side (require_permission("integrations",
          // "configs", ...)), not require_owner, so no RequireOwner wrapper here either.
          { path: "/integrations", element: <IntegrationListPage /> },
          { path: "/integrations/:configId", element: <IntegrationDetailsPage /> },
          // Module 9C — Phase 1 deployment scope: Message Center isn't shipping yet.
          { path: "/communication", element: <ComingSoonPage title="Message Center" /> },
          // Administration — Phase 1 deployment scope: not shipping yet. Every child path
          // (lead-capture, employees incl. sub-routes, roles, departments/designations,
          // temporary access, geo exceptions) resolves here since this layout renders no
          // <Outlet/> for them — a typed-in deep link lands on the same Coming Soon page.
          {
            element: <ComingSoonPage title="Administration" />,
            children: [
              { path: "/lead-capture", element: <ComingSoonPage title="Administration" /> },
              {
                element: <RequireOwner />,
                children: [
                  {
                    path: "/employees",
                    element: <EmployeesLayout />,
                    children: [
                      { index: true, element: <EmployeeListPage /> },
                      { path: "new", element: <CreateEmployeePage /> },
                      {
                        path: "documents",
                        element: (
                          <EmployeeModulePlaceholderPage
                            title="Documents"
                            description="A company-wide employee document overview will appear here once this module is enabled."
                          />
                        ),
                      },
                      {
                        path: "activity",
                        element: (
                          <EmployeeModulePlaceholderPage
                            title="Employee Activity"
                            description="A company-wide employee activity overview will appear here once this module is enabled."
                          />
                        ),
                      },
                    ],
                  },
                  { path: "/roles", element: <RoleListPage /> },
                  { path: "/settings/departments", element: <DepartmentsPage /> },
                  { path: "/settings/designations", element: <DesignationsPage /> },
                  { path: "/temporary-access", element: <TemporaryAccessPage /> },
                  { path: "/geo-exceptions", element: <GeoExceptionPage /> },
                ],
              },
            ],
          },
          {
            // Owner Account Management — Primary Owner creating/editing/deactivating
            // Secondary Owner accounts. Not part of the Administration ComingSoon bundle
            // above (Employees/Roles/etc.): this is a real, shipping feature of its own,
            // gated by RequirePrimaryOwner (Secondary Owners are redirected away, same as
            // RequireOwner does to a non-Owner elsewhere) — the backend independently
            // enforces the same restriction on every request (see require_primary_owner).
            element: <RequirePrimaryOwner />,
            children: [
              { path: "/owner-accounts", element: <OwnerAccountListPage /> },
              { path: "/owner-accounts/new", element: <CreateSecondaryOwnerPage /> },
              { path: "/owner-accounts/:ownerId/edit", element: <EditSecondaryOwnerPage /> },
            ],
          },
          {
            element: <RequireOwner />,
            children: [
              // Per-record detail/edit pages — Administration isn't part of Phase 1.
              { path: "/employees/:employeeId", element: <ComingSoonPage title="Administration" /> },
              { path: "/employees/:employeeId/edit", element: <ComingSoonPage title="Administration" /> },
              { path: "/employees/:employeeId/sessions", element: <ComingSoonPage title="Administration" /> },
              { path: "/employees/:employeeId/login-history", element: <ComingSoonPage title="Administration" /> },
              { path: "/roles/:roleId", element: <ComingSoonPage title="Administration" /> },
              { path: "/roles/:roleId/permissions", element: <ComingSoonPage title="Administration" /> },
              { path: "/roles/:roleId/assign", element: <ComingSoonPage title="Administration" /> },
              {
                // Phase 1 deployment scope trims Settings to just the master data the
                // in-scope Loan/Insurance Management modules read from (Loan Products,
                // Insurance Products, Document Types, Status Masters — the latter lives
                // outside this tab strip, see below). Everything else in Settings goes
                // Coming Soon; SettingsHomePage's own tile list is trimmed to match.
                element: <SettingsLayout />,
                children: [
                  { path: "/settings", element: <SettingsHomePage /> },
                  { path: "/settings/lead-sources", element: <ComingSoonPage title="Lead Sources" /> },
                  { path: "/settings/loan-products", element: <LoanProductsPage /> },
                  { path: "/settings/insurance-products", element: <InsuranceProductsPage /> },
                  { path: "/settings/document-types", element: <DocumentTypesPage /> },
                  { path: "/settings/reminder-rules", element: <ComingSoonPage title="Reminder Rules" /> },
                ],
              },
              // Not part of the trimmed Settings tab list. Status Masters stays real —
              // Loan/Insurance Management read from it. Everything else here is Coming Soon.
              { path: "/settings/branches", element: <ComingSoonPage title="Branches" /> },
              { path: "/settings/product-schemas", element: <ComingSoonPage title="Product Schemas" /> },
              { path: "/settings/product-schemas/compare", element: <ComingSoonPage title="Product Schemas" /> },
              { path: "/settings/product-schemas/:schemaId", element: <ComingSoonPage title="Product Schemas" /> },
              { path: "/settings/status-masters", element: <StatusMastersPage /> },
              { path: "/settings/notification-templates", element: <ComingSoonPage title="Notification Templates" /> },
              { path: "/settings/api-settings", element: <ComingSoonPage title="API Settings" /> },
              { path: "/settings/company", element: <ComingSoonPage title="Company Settings" /> },
              // Module 7 — Phase 1 deployment scope: the Owner-side Referral Partners
              // management module (partner list, commission rules/ledger) isn't shipping
              // yet. The Referral Partner's own login portal (/referral-portal/*) is a
              // separate role's destination and is unaffected — see router's own portal
              // block below.
              {
                element: <ComingSoonPage title="Referral Partners" />,
                children: [
                  { path: "/referral-partners", element: <ComingSoonPage title="Referral Partners" /> },
                  { path: "/commission-rules", element: <ComingSoonPage title="Referral Partners" /> },
                  { path: "/commission-ledger", element: <ComingSoonPage title="Referral Partners" /> },
                ],
              },
            ],
          },
        ],
      },
      {
        // Customer Portal — its own shell (not AppShell/Sidebar), see
        // CustomerPortalLayout's docstring.
        element: <RequireCustomer />,
        children: [
          {
            element: <CustomerPortalLayout />,
            children: [
              { path: "/portal", element: <PortalHomePage /> },
              { path: "/portal/profile/setup", element: <CompleteProfilePage /> },
              { path: "/portal/profile", element: <ProfilePage /> },
              { path: "/portal/profile/sessions", element: <SessionsPage backTo="/portal/profile" /> },
              { path: "/portal/applications", element: <ApplicationListPage /> },
              { path: "/portal/applications/new", element: <ProductSelectionPage /> },
              { path: "/portal/applications/:id", element: <ApplicationPage /> },
              { path: "/portal/applications/:id/timeline", element: <ApplicationTimelinePage /> },
              { path: "/portal/documents", element: <DocumentsPage /> },
              { path: "/portal/messages", element: <MessagesPage /> },
              { path: "/portal/notifications", element: <MessagesPage /> },
              { path: "/portal/support", element: <SupportPage /> },
            ],
          },
        ],
      },
      {
        // Referral Partner Portal (Module 7) — its own shell, mirroring the Customer
        // Portal's own separation from Dashboard's AppShell/Sidebar.
        element: <RequireReferralPartner />,
        children: [
          {
            element: <ReferralPartnerPortalLayout />,
            children: [
              { path: "/referral-portal", element: <ReferralPartnerDashboardPage /> },
              { path: "/referral-portal/leads", element: <ReferralPartnerLeadsPage /> },
              { path: "/referral-portal/commissions", element: <ReferralPartnerCommissionHistoryPage /> },
            ],
          },
        ],
      },
    ],
  },
]);
