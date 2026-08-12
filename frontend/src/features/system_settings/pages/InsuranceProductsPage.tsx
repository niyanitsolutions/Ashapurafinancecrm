import { insuranceProductsApi } from "@/features/system_settings/api";
import { NamedMasterDataPage } from "@/features/system_settings/pages/NamedMasterDataPage";

export function InsuranceProductsPage() {
  return <NamedMasterDataPage title="Insurance Products" createPlaceholder="e.g. Health" api={insuranceProductsApi} />;
}
