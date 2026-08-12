import {
  activateDesignation,
  createDesignation,
  deactivateDesignation,
  listDesignations,
  updateDesignation,
} from "@/features/system_settings/api";
import { NamedMasterDataPage } from "@/features/system_settings/pages/NamedMasterDataPage";

const api = {
  list: listDesignations,
  create: createDesignation,
  update: updateDesignation,
  activate: activateDesignation,
  deactivate: deactivateDesignation,
};

export function DesignationsPage() {
  return <NamedMasterDataPage title="Designations" createPlaceholder="e.g. Manager" api={api} />;
}
