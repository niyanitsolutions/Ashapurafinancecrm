import { documentTypesApi } from "@/features/system_settings/api";
import { NamedMasterDataPage } from "@/features/system_settings/pages/NamedMasterDataPage";

export function DocumentTypesPage() {
  return <NamedMasterDataPage title="Document Types" createPlaceholder="e.g. PAN" api={documentTypesApi} showPasswordSupport />;
}
