import { loanProductsApi } from "@/features/system_settings/api";
import { NamedMasterDataPage } from "@/features/system_settings/pages/NamedMasterDataPage";

export function LoanProductsPage() {
  return <NamedMasterDataPage title="Loan Products" createPlaceholder="e.g. Personal Loan" api={loanProductsApi} />;
}
