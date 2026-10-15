# CRM route and shared UI coverage

Generated from the actual TypeScript AST in frontend/src/app/router.tsx at the current checkout.
164 rendered route/layout/redirect entries; pathless layouts share their parent path.
No route or authorization was changed. Global content tokens apply across the CRM;
shared-component adoption does not certify a bespoke redesign or browser acceptance
for every page. Screenshot coverage and remaining per-page work are reported separately.
Voice's :section route also dispatches existing panels internally; see VoiceAssistantPage.

| Route | Component | Source import | Shared content components | Inherited guards |
|---|---|---|---|---|
| /login | LoginPage | @/features/auth/pages/LoginPage | global tokens; custom page structure | public / inherited application routing |
| /forgot-password | ForgotPasswordPage | @/features/auth/pages/ForgotPasswordPage | Button, FormField | public / inherited application routing |
| /verify-otp | OtpVerificationPage | @/features/auth/pages/OtpVerificationPage | Button, FormField | public / inherited application routing |
| /reset-password | ResetPasswordPage | @/features/auth/pages/ResetPasswordPage | Button, FormField | public / inherited application routing |
| /register | RegisterPage | @/features/customer/pages/RegisterPage | Button, FormField | public / inherited application routing |
| /create-account | CreateAccountPage | @/features/owner/pages/CreateAccountPage | Button, FormField | public / inherited application routing |
| /apply/:secureCode | SecureLinkLandingPage | @/features/customer/pages/SecureLinkLandingPage | Card | public / inherited application routing |
| / | HomeRedirect | @/app/HomeRedirect | global tokens; custom page structure | <RequireAuth /> |
| /force-change-password | ForceChangePasswordPage | @/features/auth/pages/ForceChangePasswordPage | Button, FormField | <RequireAuth /> |
| / | AppShell | @/components/layout/AppShell | SimplePageLayout | <RequireAuth /> |
| /dashboard | DashboardPage | @/features/dashboard/pages/DashboardPage | Card | <RequireAuth /> |
| /profile | EmployeeProfilePage | @/features/employee/pages/EmployeeProfilePage | SimplePageLayout, Button, FormField | <RequireAuth /> |
| /profile/change-password | ChangePasswordPage | @/features/auth/pages/ChangePasswordPage | SimplePageLayout, Button, FormField | <RequireAuth /> |
| /profile/sessions | SessionsPage | @/features/auth/pages/SessionsPage | SimplePageLayout, Button | <RequireAuth /> |
| /profile/login-history | EmployeeLoginHistoryPage | @/features/employee/pages/EmployeeLoginHistoryPage | SimplePageLayout | <RequireAuth /> |
| /leads | LeadsLayout | @/features/leads/pages/LeadsLayout | ModuleTabs | <RequireAuth /> |
| /leads | LeadListPage | @/features/leads/pages/LeadListPage | Button, DataTable | <RequireAuth /> |
| /leads/my | LeadListPage | @/features/leads/pages/LeadListPage | Button, DataTable | <RequireAuth /> |
| /leads/document-collection | LeadListPage | @/features/leads/pages/LeadListPage | Button, DataTable | <RequireAuth /> |
| /leads/rejected | LeadListPage | @/features/leads/pages/LeadListPage | Button, DataTable | <RequireAuth /> |
| /leads/assigned | LeadListPage | @/features/leads/pages/LeadListPage | Button, DataTable | <RequireAuth /> |
| /leads/top-up | TopUpLoanListPage | @/features/loan_management/pages/TopUpLoanListPage | Button, CaseListPage | <RequireAuth /> |
| /leads/re-eligible | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /leads/new | CreateLeadPage | @/features/leads/pages/CreateLeadPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequirePermission module="leads" resource="leads" action="create" redirectTo="/leads" /> |
| /leads/:leadId | LeadDetailsPage | @/features/leads/pages/LeadDetailsPage | SimplePageLayout, Button, FormField | <RequireAuth /> |
| / | CustomersLayout | @/features/customer/pages/CustomersLayout | ModuleTabs | <RequireAuth /> |
| /customers | CustomerListPage | @/features/customer/pages/CustomerListPage | Button, DataTable | <RequireAuth /> |
| /applications | StaffApplicationListPage | @/features/customer/pages/StaffApplicationListPage | Button, DataTable | <RequireAuth /> |
| /customers/:customerId | CustomerDetailsPage | @/features/customer/pages/CustomerDetailsPage | SimplePageLayout, Button | <RequireAuth /> |
| /applications/:applicationId | StaffApplicationDetailsPage | @/features/customer/pages/StaffApplicationDetailsPage | SimplePageLayout, Card, Button, FormField | <RequireAuth /> |
| /loan-cases | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-cases/:caseId | LoanCaseDetailsPage | @/features/loan_management/pages/LoanCaseDetailsPage | SimplePageLayout, Button, FormField | <RequireAuth /> |
| /loan-management/cases/:caseId | LoanCaseDetailsPage | @/features/loan_management/pages/LoanCaseDetailsPage | SimplePageLayout, Button, FormField | <RequireAuth /> |
| /insurance-cases | InsuranceCaseListPage | @/features/insurance_management/pages/InsuranceCaseListPage | Button, CaseListPage | <RequireAuth /> |
| /invoices | InvoiceListPage | @/features/invoices/InvoiceListPage | SimplePageLayout, Button | <RequireAuth /> → <RequirePermission module="invoices" resource="invoices" action="view" redirectTo="/" /> |
| /invoices/:invoiceId | InvoiceViewPage | @/features/invoices/InvoiceViewPage | SimplePageLayout, Button | <RequireAuth /> → <RequirePermission module="invoices" resource="invoices" action="view" redirectTo="/" /> |
| /voice-assistant | VoiceAssistantPage | @/features/voice_assistant/VoiceAssistantPage | SimplePageLayout | <RequireAuth /> → <RequirePermission module="voice_assistant" resource="calls" action="view" redirectTo="/" /> |
| /voice-assistant/:section | VoiceAssistantPage | @/features/voice_assistant/VoiceAssistantPage | SimplePageLayout | <RequireAuth /> → <RequirePermission module="voice_assistant" resource="calls" action="view" redirectTo="/" /> |
| /invoices/new | InvoiceFormPage | @/features/invoices/InvoiceFormPage | SimplePageLayout, Button | <RequireAuth /> → <RequirePermission module="invoices" resource="invoices" action="create" redirectTo="/invoices" /> |
| /invoices/:invoiceId/edit | InvoiceFormPage | @/features/invoices/InvoiceFormPage | SimplePageLayout, Button | <RequireAuth /> → <RequirePermission module="invoices" resource="invoices" action="edit" redirectTo="/invoices" /> |
| /insurance-cases/:caseId | InsuranceCaseDetailsPage | @/features/insurance_management/pages/InsuranceCaseDetailsPage | SimplePageLayout, Button, FormField | <RequireAuth /> |
| /loan-management | LoanManagementLayout | @/features/loan_management/pages/LoanManagementLayout | ModuleTabs | <RequireAuth /> |
| /loan-management | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /loan-management/cases | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-management/credit-evaluation | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-management/offer-acceptance | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-management/additional-documents | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-management/rv-ov-ref | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-management/esign-nach-kyc | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-management/final-evaluation | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-management/send-for-disbursement | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-management/disbursements | DisbursementsPage | @/features/loan_management/pages/DisbursementsPage | Button, DataTable | <RequireAuth /> |
| /loan-management/on-hold | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-management/rejected | LoanCaseListPage | @/features/loan_management/pages/LoanCaseListPage | CaseListPage | <RequireAuth /> |
| /loan-management/re-eligible | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /insurance-management | InsuranceManagementLayout | @/features/insurance_management/pages/InsuranceManagementLayout | ModuleTabs | <RequireAuth /> |
| /insurance-management | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /insurance-management/fresh-leads | InsuranceCaseListPage | @/features/insurance_management/pages/InsuranceCaseListPage | Button, CaseListPage | <RequireAuth /> |
| /insurance-management/policy-document | InsuranceCaseListPage | @/features/insurance_management/pages/InsuranceCaseListPage | Button, CaseListPage | <RequireAuth /> |
| /insurance-management/policy-login | InsuranceCaseListPage | @/features/insurance_management/pages/InsuranceCaseListPage | Button, CaseListPage | <RequireAuth /> |
| /insurance-management/payment | InsuranceCaseListPage | @/features/insurance_management/pages/InsuranceCaseListPage | Button, CaseListPage | <RequireAuth /> |
| /insurance-management/policy-issued | InsuranceCaseListPage | @/features/insurance_management/pages/InsuranceCaseListPage | Button, CaseListPage | <RequireAuth /> |
| /insurance-management/re-eligible | InsuranceCaseListPage | @/features/insurance_management/pages/InsuranceCaseListPage | Button, CaseListPage | <RequireAuth /> |
| /insurance-management/rejected | InsuranceCaseListPage | @/features/insurance_management/pages/InsuranceCaseListPage | Button, CaseListPage | <RequireAuth /> |
| /insurance-management/on-hold | InsuranceCaseListPage | @/features/insurance_management/pages/InsuranceCaseListPage | Button, CaseListPage | <RequireAuth /> |
| /insurance-management/cases | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /insurance-management/policies-issued | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /insurance-management/recruitment | RecruitmentLayout | @/features/recruitment/pages/RecruitmentLayout | ModuleTabs | <RequireAuth /> |
| /insurance-management/recruitment | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /insurance-management/recruitment/fresh | RecruitmentListPage | @/features/recruitment/pages/RecruitmentListPage | Button, DataTable | <RequireAuth /> |
| /insurance-management/recruitment/bop | RecruitmentListPage | @/features/recruitment/pages/RecruitmentListPage | Button, DataTable | <RequireAuth /> |
| /insurance-management/recruitment/doc-collection | RecruitmentListPage | @/features/recruitment/pages/RecruitmentListPage | Button, DataTable | <RequireAuth /> |
| /insurance-management/recruitment/exam-fee-status | RecruitmentListPage | @/features/recruitment/pages/RecruitmentListPage | Button, DataTable | <RequireAuth /> |
| /insurance-management/recruitment/examination | RecruitmentListPage | @/features/recruitment/pages/RecruitmentListPage | Button, DataTable | <RequireAuth /> |
| /insurance-management/recruitment/re-examination | RecruitmentListPage | @/features/recruitment/pages/RecruitmentListPage | Button, DataTable | <RequireAuth /> |
| /insurance-management/recruitment/agency-code | AgencyCodeListPage | @/features/recruitment/pages/AgencyCodeListPage | Button, DataTable | <RequireAuth /> |
| /insurance-management/recruitment/rejected | RecruitmentListPage | @/features/recruitment/pages/RecruitmentListPage | Button, DataTable | <RequireAuth /> |
| /insurance-management/recruitment/doc-collection/examination | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /insurance-management/recruitment/doc-collection/re-examination | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /insurance-management/recruitment/doc-collection/agency-code | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /insurance-management/recruitment/:recruitmentId | RecruitmentDetailsPage | @/features/recruitment/pages/RecruitmentDetailsPage | global tokens; custom page structure | <RequireAuth /> |
| /insurance-management/advisors | AdvisorListPage | @/features/recruitment/pages/AdvisorListPage | Button, DataTable | <RequireAuth /> |
| /insurance-management/advisors/qr | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /insurance-management/advisors/non-qr | Navigate | react-router-dom | layout/redirect | <RequireAuth /> |
| /insurance-management/advisors/:advisorId | AdvisorDetailsPage | @/features/recruitment/pages/AdvisorDetailsPage | Button, DataTable | <RequireAuth /> |
| /insurance-management/analytics | InsuranceAnalyticsPage | @/features/insurance_management/pages/InsuranceAnalyticsPage | Button | <RequireAuth /> |
| /tasks | TaskListPage | @/features/reminders/pages/TaskListPage | SimplePageLayout, Button, DataTable | <RequireAuth /> |
| /notifications | NotificationListPage | @/features/reminders/pages/NotificationListPage | SimplePageLayout | <RequireAuth /> |
| /reminder-rules | ReminderRulesPage | @/features/reminders/pages/ReminderRulesPage | SimplePageLayout, Card | <RequireAuth /> |
| / | ReportsLayout | @/features/reporting/pages/ReportsLayout | ModuleTabs | <RequireAuth /> |
| /reports | ReportCatalogPage | @/features/reporting/pages/ReportCatalogPage | SimplePageLayout | <RequireAuth /> |
| /scheduled-reports | ScheduledReportsPage | @/features/reporting/pages/ScheduledReportsPage | SimplePageLayout, Button, FormField | <RequireAuth /> |
| /reports/:reportKey | ReportViewerPage | @/features/reporting/pages/ReportViewerPage | SimplePageLayout, Button | <RequireAuth /> |
| /integrations | IntegrationListPage | @/features/integrations/pages/IntegrationListPage | SimplePageLayout, Button | <RequireAuth /> |
| /integrations/:configId | IntegrationDetailsPage | @/features/integrations/pages/IntegrationDetailsPage | SimplePageLayout, Button | <RequireAuth /> |
| /communication | CommunicationPage | @/features/communication/pages/CommunicationPage | SimplePageLayout, Button | <RequireAuth /> |
| /support-tickets | SupportTicketListPage | @/features/support/pages/SupportTicketListPage | SimplePageLayout, Button, DataTable | <RequireAuth /> |
| /conversations | ConversationsPage | @/features/messaging/pages/ConversationsPage | SimplePageLayout | <RequireAuth /> |
| /lead-capture | LeadCapturePage | @/features/lead_capture/pages/LeadCapturePage | SimplePageLayout | <RequireAuth /> |
| /bin | BinPage | @/features/bin/pages/BinPage | Button, DataTable | <RequireAuth /> → <RequireOwner /> |
| /employees | EmployeesLayout | @/features/employee/pages/EmployeesLayout | ModuleTabs | <RequireAuth /> → <RequireOwner /> |
| /employees | EmployeeListPage | @/features/employee/pages/EmployeeListPage | SimplePageLayout, Button | <RequireAuth /> → <RequireOwner /> |
| /employees/new | CreateEmployeePage | @/features/employee/pages/CreateEmployeePage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /employees/documents | EmployeeDocumentsOverviewPage | @/features/employee/pages/EmployeeDocumentsOverviewPage | SimplePageLayout | <RequireAuth /> → <RequireOwner /> |
| /employees/activity | EmployeeActivityOverviewPage | @/features/employee/pages/EmployeeActivityOverviewPage | SimplePageLayout | <RequireAuth /> → <RequireOwner /> |
| /roles | RoleListPage | @/features/access_control/pages/RoleListPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /settings/departments | DepartmentsPage | @/features/system_settings/pages/DepartmentsPage | global tokens; custom page structure | <RequireAuth /> → <RequireOwner /> |
| /settings/designations | DesignationsPage | @/features/system_settings/pages/DesignationsPage | global tokens; custom page structure | <RequireAuth /> → <RequireOwner /> |
| /temporary-access | TemporaryAccessPage | @/features/access_control/pages/TemporaryAccessPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /owner-accounts | OwnerAccountListPage | @/features/owner/pages/OwnerAccountListPage | SimplePageLayout, Button | <RequireAuth /> → <RequirePrimaryOwner /> |
| /owner-accounts/new | CreateSecondaryOwnerPage | @/features/owner/pages/CreateSecondaryOwnerPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequirePrimaryOwner /> |
| /owner-accounts/:ownerId/edit | EditSecondaryOwnerPage | @/features/owner/pages/EditSecondaryOwnerPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequirePrimaryOwner /> |
| /employees/:employeeId | EmployeeDetailsPage | @/features/employee/pages/EmployeeDetailsPage | SimplePageLayout, Button | <RequireAuth /> → <RequireOwner /> |
| /employees/:employeeId/edit | EditEmployeePage | @/features/employee/pages/EditEmployeePage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /employees/:employeeId/sessions | EmployeeSessionsPage | @/features/employee/pages/EmployeeSessionsPage | SimplePageLayout | <RequireAuth /> → <RequireOwner /> |
| /employees/:employeeId/login-history | EmployeeLoginHistoryPage | @/features/employee/pages/EmployeeLoginHistoryPage | SimplePageLayout | <RequireAuth /> → <RequireOwner /> |
| /roles/:roleId | RoleDetailsPage | @/features/access_control/pages/RoleDetailsPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /roles/:roleId/permissions | PermissionMatrixPage | @/features/access_control/pages/PermissionMatrixPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /roles/:roleId/assign | AssignRolePage | @/features/access_control/pages/AssignRolePage | SimplePageLayout, Button | <RequireAuth /> → <RequireOwner /> |
| / | SettingsLayout | @/features/system_settings/pages/SettingsLayout | ModuleTabs | <RequireAuth /> → <RequireOwner /> |
| /settings | SettingsHomePage | @/features/system_settings/pages/SettingsHomePage | SimplePageLayout, Card | <RequireAuth /> → <RequireOwner /> |
| /settings/lead-sources | LeadSourcesPage | @/features/system_settings/pages/LeadSourcesPage | Button | <RequireAuth /> → <RequireOwner /> |
| /settings/loan-products | LoanProductsPage | @/features/system_settings/pages/LoanProductsPage | global tokens; custom page structure | <RequireAuth /> → <RequireOwner /> |
| /settings/insurance-categories | InsuranceCategoriesPage | @/features/system_settings/pages/InsuranceCategoriesPage | global tokens; custom page structure | <RequireAuth /> → <RequireOwner /> |
| /settings/insurance-products | InsuranceProductsPage | @/features/system_settings/pages/InsuranceProductsPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /settings/document-types | DocumentTypesPage | @/features/system_settings/pages/DocumentTypesPage | global tokens; custom page structure | <RequireAuth /> → <RequireOwner /> |
| /settings/geo-fencing | GeoFencingPage | @/features/geo_fencing/pages/GeoFencingPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /geo-exceptions | GeoExceptionPage | @/features/access_control/pages/GeoExceptionPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /settings/communication-providers | CommunicationProvidersPage | @/features/communication/pages/CommunicationProvidersPage | SimplePageLayout, Button | <RequireAuth /> → <RequireOwner /> |
| /settings/reminder-rules | ReminderRulesPage | @/features/reminders/pages/ReminderRulesPage | SimplePageLayout, Card | <RequireAuth /> → <RequireOwner /> |
| /settings/branches | BranchesPage | @/features/system_settings/pages/BranchesPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /settings/status-masters | StatusMastersPage | @/features/system_settings/pages/StatusMastersPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /settings/notification-templates | NotificationTemplatesPage | @/features/system_settings/pages/NotificationTemplatesPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /settings/company | CompanySettingsPage | @/features/system_settings/pages/CompanySettingsPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /settings/invoices | InvoiceSettingsPage | @/features/invoices/InvoiceSettingsPage | SimplePageLayout, Button | <RequireAuth /> → <RequireOwner /> |
| /settings/product-schemas | ProductSchemasPage | @/features/customer/pages/ProductSchemasPage | SimplePageLayout, Button | <RequireAuth /> → <RequireOwner /> |
| /settings/product-schemas/compare | SchemaComparePage | @/features/customer/pages/SchemaComparePage | SimplePageLayout | <RequireAuth /> → <RequireOwner /> |
| /settings/product-schemas/:schemaId | SchemaEditorPage | @/features/customer/pages/SchemaEditorPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /settings/api-settings | Navigate | react-router-dom | layout/redirect | <RequireAuth /> → <RequireOwner /> |
| / | ReferralPartnersLayout | @/features/referral_partner_management/pages/ReferralPartnersLayout | ModuleTabs | <RequireAuth /> → <RequireOwner /> |
| /commission-rules | CommissionRulesPage | @/features/referral_partner_management/pages/CommissionRulesPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| /commission-ledger | CommissionLedgerPage | @/features/referral_partner_management/pages/CommissionLedgerPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireOwner /> |
| / | ReferralPartnersLayout | @/features/referral_partner_management/pages/ReferralPartnersLayout | ModuleTabs | <RequireAuth /> |
| /referral-partners | ReferralPartnerListPage | @/features/referral_partner_management/pages/ReferralPartnerListPage | SimplePageLayout, Button, FormField | <RequireAuth /> |
| / | CustomerPortalLayout | @/features/customer/components/CustomerPortalLayout | global tokens; custom page structure | <RequireAuth /> → <RequireCustomer /> |
| /portal | PortalHomePage | @/features/customer/pages/PortalHomePage | Card | <RequireAuth /> → <RequireCustomer /> |
| /portal/profile/setup | CompleteProfilePage | @/features/customer/pages/CompleteProfilePage | Button, FormField | <RequireAuth /> → <RequireCustomer /> |
| /portal/profile | ProfilePage | @/features/customer/pages/ProfilePage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireCustomer /> |
| /portal/profile/sessions | SessionsPage | @/features/auth/pages/SessionsPage | SimplePageLayout, Button | <RequireAuth /> → <RequireCustomer /> |
| /portal/applications | ApplicationListPage | @/features/customer/pages/ApplicationListPage | SimplePageLayout, Card | <RequireAuth /> → <RequireCustomer /> |
| /portal/applications/new | ProductSelectionPage | @/features/customer/pages/ProductSelectionPage | global tokens; custom page structure | <RequireAuth /> → <RequireCustomer /> |
| /portal/applications/:id | ApplicationPage | @/features/customer/pages/ApplicationPage | Button, FormField | <RequireAuth /> → <RequireCustomer /> |
| /portal/applications/:id/timeline | ApplicationTimelinePage | @/features/customer/pages/ApplicationTimelinePage | SimplePageLayout | <RequireAuth /> → <RequireCustomer /> |
| /portal/applications/:id/loan-offers | LoanOffersPage | @/features/customer/pages/LoanOffersPage | SimplePageLayout, Button | <RequireAuth /> → <RequireCustomer /> |
| /portal/applications/:id/additional-documents | AdditionalDocumentsPage | @/features/customer/pages/AdditionalDocumentsPage | SimplePageLayout, Button | <RequireAuth /> → <RequireCustomer /> |
| /portal/documents | DocumentsPage | @/features/customer/pages/DocumentsPage | SimplePageLayout | <RequireAuth /> → <RequireCustomer /> |
| /portal/messages | ConversationPage | @/features/customer/pages/ConversationPage | SimplePageLayout | <RequireAuth /> → <RequireCustomer /> |
| /portal/notifications | MessagesPage | @/features/customer/pages/MessagesPage | SimplePageLayout | <RequireAuth /> → <RequireCustomer /> |
| /portal/alerts | NotificationListPage | @/features/reminders/pages/NotificationListPage | SimplePageLayout | <RequireAuth /> → <RequireCustomer /> |
| /portal/support | SupportPage | @/features/customer/pages/SupportPage | SimplePageLayout, Button, FormField | <RequireAuth /> → <RequireCustomer /> |
| / | ReferralPartnerPortalLayout | @/features/referral_partner_management/components/ReferralPartnerPortalLayout | global tokens; custom page structure | <RequireAuth /> → <RequireReferralPartner /> |
| /referral-portal | ReferralPartnerDashboardPage | @/features/referral_partner_management/pages/ReferralPartnerDashboardPage | Card | <RequireAuth /> → <RequireReferralPartner /> |
| /referral-portal/leads | ReferralPartnerLeadsPage | @/features/referral_partner_management/pages/ReferralPartnerLeadsPage | Button | <RequireAuth /> → <RequireReferralPartner /> |
| /referral-portal/commissions | ReferralPartnerCommissionHistoryPage | @/features/referral_partner_management/pages/ReferralPartnerCommissionHistoryPage | global tokens; custom page structure | <RequireAuth /> → <RequireReferralPartner /> |
