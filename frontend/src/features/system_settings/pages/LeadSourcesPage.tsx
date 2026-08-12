import { leadSourcesApi } from "@/features/system_settings/api";
import { NamedMasterDataPage } from "@/features/system_settings/pages/NamedMasterDataPage";

export function LeadSourcesPage() {
  return <NamedMasterDataPage title="Lead Sources" createPlaceholder="e.g. Website" api={leadSourcesApi} />;
}
