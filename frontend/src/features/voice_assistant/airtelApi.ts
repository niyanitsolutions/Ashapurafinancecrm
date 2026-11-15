import { apiRequest } from "@/shared/api/client";

export interface AirtelVoiceConnection {
  version: number;
  public_origin: string | null;
  account_sid: string | null;
  caller_id: string | null;
  call_flow_id: string | null;
  requested_concurrency: number;
  credentials_configured: boolean;
  connection_status: string;
  provider_authentication: string;
  webhook_status: string;
  audio_status: string;
  capacity_status: string;
  recording_api_origin: string;
  c2c_path: string;
  recording_path: string;
  media_url: string | null;
  events_url: string | null;
  cdr_url: string | null;
  blockers: string[];
  last_test: AirtelLocalEvidence | null;
}
export interface AirtelLocalEvidence {
  status: string;
  scope: string;
  message: string;
  provider_verified: false;
  calls_placed: 0;
}
export interface AirtelVoiceInput {
  version: number;
  public_origin: string | null;
  account_sid: string | null;
  caller_id: string | null;
  call_flow_id: string | null;
  requested_concurrency: number;
  app_id?: string;
  api_key?: string;
  clear_credentials: boolean;
}
const root = "/voice-assistant/airtel";
export const getAirtelVoice = () => apiRequest<AirtelVoiceConnection>(`${root}/connection`);
export const saveAirtelVoice = (body: AirtelVoiceInput) => apiRequest<AirtelVoiceConnection>(`${root}/connection`, { method: "PUT", body: JSON.stringify(body) });
export const validateAirtelVoice = () => apiRequest<AirtelLocalEvidence>(`${root}/tests/local`, { method: "POST" });
