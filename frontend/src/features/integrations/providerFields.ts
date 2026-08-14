// Section is optional UI grouping metadata only (Stage 4 MSG91 config UI hardening) —
// consumed by Msg91ConfigForm to render A. Credentials / B. Channel Configuration /
// C. Delivery & Webhook Configuration; every other consumer (CreateConfigForm,
// IntegrationDetailsPage) ignores it and renders fields in flat array order, unchanged.
export type ProviderFieldSection = "credentials" | "channel" | "webhook";

export interface ProviderField {
  key: string;
  label: string;
  secret?: boolean;
  toggle?: boolean;
  section?: ProviderFieldSection;
  optional?: boolean;
  helpText?: string;
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
  { key: "host", label: "Host", section: "channel" },
  { key: "port", label: "Port", section: "channel" },
  { key: "username", label: "Username", section: "credentials" },
  { key: "password", label: "Password", secret: true, section: "credentials" },
  { key: "tls_ssl", label: "TLS/SSL", toggle: true, section: "channel" },
  { key: "from_name", label: "From Name", section: "channel" },
  { key: "from_email", label: "From Email", section: "channel" },
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

// MSG91 (Stage 2 of the Geo Fencing/Temporary Permissions/MSG91 request) — see
// docs/COMMUNICATION.md. Email deliberately has no MSG91-specific field set: MSG91
// issues standard SMTP relay credentials, so it reuses EMAIL_SMTP_FIELDS unchanged.
export const MSG91_SMS_FIELDS: ProviderField[] = [
  { key: "auth_key", label: "Auth Key", secret: true, section: "credentials", helpText: "Your MSG91 account Auth Key (Dashboard → API → Auth Key)." },
  { key: "sender_id", label: "Sender ID", section: "channel", helpText: "The approved 6-character DLT sender ID, e.g. AFSFIN." },
  { key: "flow_id", label: "SMS Template ID (Flow ID)", section: "channel", helpText: "The Flow ID of the approved SMS template in MSG91." },
  { key: "dlt_template_id", label: "DLT Template ID", section: "channel", optional: true, helpText: "TRAI DLT-registered template ID, required in India for promotional/transactional SMS. Leave blank if not applicable." },
  // Set this to any value you choose, then configure MSG91's own SMS DLR webhook URL as
  // {API_BASE_URL}/communication/webhooks/msg91?secret=<same value> — see the Delivery
  // Webhook panel on the Communication Providers page.
  { key: "webhook_secret", label: "Webhook Secret", secret: true, section: "webhook", helpText: "Shared secret for verifying inbound MSG91 delivery report callbacks." },
];

export const MSG91_WHATSAPP_FIELDS: ProviderField[] = [
  { key: "auth_key", label: "Auth Key", secret: true, section: "credentials", helpText: "Your MSG91 account Auth Key (Dashboard → API → Auth Key)." },
  { key: "integrated_number", label: "Integrated WhatsApp Number", section: "channel", helpText: "The WhatsApp Business number connected in MSG91, in international format." },
  {
    key: "whatsapp_template_name", label: "Approved WhatsApp Template Name", section: "channel", optional: true,
    helpText: "Default template used when a message doesn't specify its own — set per-template overrides in Message Center to use a different template for a specific message.",
  },
  { key: "whatsapp_template_language", label: "Template Language", section: "channel", optional: true, helpText: "e.g. en, en_US — defaults to en if left blank." },
  { key: "whatsapp_template_namespace", label: "Template Namespace", section: "channel", optional: true, helpText: "Required only if your WhatsApp Business Account uses namespaced templates." },
  { key: "webhook_secret", label: "Webhook Secret", secret: true, section: "webhook", helpText: "Shared secret for verifying inbound MSG91 delivery report callbacks." },
];

export function fieldsFor(integrationType: string, provider: string): ProviderField[] {
  if (integrationType === "meta") return META_FIELDS;
  if (integrationType === "whatsapp") return provider === "msg91" ? MSG91_WHATSAPP_FIELDS : WHATSAPP_FIELDS;
  if (integrationType === "sms") return provider === "msg91" ? MSG91_SMS_FIELDS : SMS_FIELDS;
  if (integrationType === "maps") return MAPS_FIELDS;
  if (integrationType === "email") return provider === "smtp" || provider === "msg91" ? EMAIL_SMTP_FIELDS : EMAIL_API_FIELDS;
  return [];
}
