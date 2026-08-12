import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

const TABS = [
  { label: "Partners", to: "/referral-partners", matchKey: "referral_partners" },
  { label: "Commission Rules", to: "/commission-rules", matchKey: "commission_rules" },
  { label: "Commission Payouts", to: "/commission-ledger", matchKey: "commission_ledger" },
];

export function ReferralPartnersLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
