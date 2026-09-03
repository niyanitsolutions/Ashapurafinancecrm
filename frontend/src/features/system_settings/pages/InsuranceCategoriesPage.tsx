import { insuranceCategoriesApi } from "@/features/system_settings/api";
import { NamedMasterDataPage } from "@/features/system_settings/pages/NamedMasterDataPage";

// Insurance Policy Leads redesign — the top of the Insurance Category -> Product
// hierarchy. Plain name+description+status master data, so it reuses the generic page.
export function InsuranceCategoriesPage() {
  return <NamedMasterDataPage title="Insurance Categories" createPlaceholder="e.g. Health Insurance" api={insuranceCategoriesApi} />;
}
