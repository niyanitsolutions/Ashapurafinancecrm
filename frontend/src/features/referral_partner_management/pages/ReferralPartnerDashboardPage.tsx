import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";
import { apiRequest } from "@/shared/api/client";
import { getOwnPartner } from "../api";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { PartnerMetrics } from "./PartnerLedgerViews";
import { PartnerReferralsPage } from "./PartnerReferralsPage";

export function ReferralPartnerDashboardPage() {
  const partner=useQuery({queryKey:["own-partner-dashboard"],queryFn:getOwnPartner});
  const policy=useQuery({queryKey:["own-partner-current-terms"],queryFn:()=>apiRequest<{requires_agreement_acceptance:boolean}>("/partner-portal/kyc"),enabled:partner.data?.kyc_status==="approved"});
  if(partner.isLoading)return <p role="status">Loading Partner dashboard?</p>;
  if(partner.error)return <ErrorBanner message={partner.error instanceof Error?partner.error.message:"Unable to load Partner profile."}/>;
  if(partner.data?.kyc_status!=="approved")return <Navigate to="/referral-portal/kyc" replace/>;
  if(policy.isLoading)return <p role="status">Checking current Partner terms...</p>;
  if(policy.error)return <ErrorBanner message={policy.error instanceof Error?policy.error.message:"Unable to check current terms."}/>;
  if(policy.data?.requires_agreement_acceptance)return <Navigate to="/referral-portal/kyc" replace/>;
  return <div className="space-y-6"><PartnerMetrics/><PartnerReferralsPage/></div>;
}
