export interface ProviderField {
  key: string;
  label: string;
  secret?: boolean;
  toggle?: boolean;
}

// Field lists per the brief's own spec, matching backend/app/features/integrations/
// constants.py:is_secret_key's naming convention (secret/token/key/password) — the
// backend never validates a fixed schema per provider (config is a flexible dict, same
// philosophy as system_settings.ApiSetting), this is purely UI guidance for which
// inputs to render.
//
// Meta only asks for App ID/App Secret here (the reused "Ashapura CRM" app's own
// credentials) — Webhook Verify Token/Secret are auto-generated server-side on create
// (see IntegrationListPage's one-time reveal panel), and the Access Token is no longer
// pasted by hand at all: IntegrationDetailsPage's "Connect Facebook" OAuth flow acquires
// a Page Access Token once App ID/Secret are saved.
export const META_FIELDS: ProviderField[] = [
  { key: "app_id", label: "App ID" },
  { key: "app_secret", label: "App Secret", secret: true },
];

export const WHATSAPP_FIELDS: ProviderField[] = [
  { key: "api_url", label: "API URL" },
  { key: "access_token", label: "Access Token", secret: true },
  { key: "phone_number_id", label: "Phone Number ID" },
  { key: "business_account_id", label: "Business Account ID" },
];

export const SMS_FIELDS: ProviderField[] = [
  { key: "api_url", label: "API URL" },
  { key: "api_key", label: "API Key", secret: true },
  { key: "sender_id", label: "Sender ID" },
];

export const EMAIL_SMTP_FIELDS: ProviderField[] = [
  { key: "host", label: "Host" },
  { key: "port", label: "Port" },
  { key: "username", label: "Username" },
  { key: "password", label: "Password", secret: true },
  { key: "tls_ssl", label: "TLS/SSL", toggle: true },
  { key: "from_name", label: "From Name" },
  { key: "from_email", label: "From Email" },
];

export const EMAIL_API_FIELDS: ProviderField[] = [
  { key: "api_key", label: "API Key", secret: true },
  { key: "api_url", label: "API URL (optional)" },
  { key: "from_name", label: "From Name" },
  { key: "from_email", label: "From Email" },
];

export const MAPS_FIELDS: ProviderField[] = [
  { key: "api_key", label: "API Key", secret: true },
  { key: "geofencing_enabled", label: "Geofencing Enabled", toggle: true },
];

export function fieldsFor(integrationType: string, provider: string): ProviderField[] {
  if (integrationType === "meta") return META_FIELDS;
  if (integrationType === "whatsapp") return WHATSAPP_FIELDS;
  if (integrationType === "sms") return SMS_FIELDS;
  if (integrationType === "maps") return MAPS_FIELDS;
  if (integrationType === "email") return provider === "smtp" ? EMAIL_SMTP_FIELDS : EMAIL_API_FIELDS;
  return [];
}
