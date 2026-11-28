import { usePermissions } from "@/features/access_control/usePermissions";
import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

const TABS = [
  { label: "Partners", to: "/referral-partners", matchKey: "referral_partners", exact: true },
  { label: "KYC Review", to: "/referral-partners/kyc-review", matchKey: "referral_partners" },
  { label: "KYC Configuration", to: "/referral-partners/kyc-settings", matchKey: "referral_partners" },
  { label: "Referral Reports", to: "/referral-partners/reports", matchKey: "referral_partners" },
  { label: "Commission Rules", to: "/commission-rules", matchKey: "commission_rules" },
  { label: "Commission Payouts", to: "/commission-ledger", matchKey: "commission_ledger" },
];

export function ReferralPartnersLayout() {
  const {isOwner}=usePermissions();
  return (
    <>
      <ModuleTabs tabs={isOwner?TABS:TABS.filter(tab=>tab.to==="/referral-partners")} />
      <Outlet />
    </>
  );
}
