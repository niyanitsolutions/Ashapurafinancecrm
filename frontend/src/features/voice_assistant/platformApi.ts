import { apiBlob, apiRequest } from "@/shared/api/client";

export type VoiceEnvironment = "test" | "production";
export type VoiceComponent = "telephony" | "stt" | "tts" | "inference" | "media" | "workers" | "recording" | "transfer" | "smartflo";
export interface PlatformState {
  environment: VoiceEnvironment; version: number; emergency_stopped: boolean;
  inbound: boolean; outbound: boolean; processing: boolean; production_eligible: boolean;
  live_implementation_available: boolean; evidence_token: string;
  components: Record<VoiceComponent, { enabled: boolean; profile_id: string | null; testing_supported: boolean }>;
  gates: { key: string; passed: boolean; remediation: string }[];
  history: { event: string; actor_id: string; at: string; reason: string }[];
}
export interface SpeechProfile { id: string; kind: "stt" | "tts"; engine: string; language: string; version: string; state: string }
export interface SpeechJob { id: string; kind: string; profile_id: string; status: string; created_at: string; finished_at: string | null; diagnostic: string | null; latency_ms: number | null; evidence: Record<string, unknown> | null; control_version: number }
const base = "/voice-assistant/platform";
export const getPlatform = (environment: VoiceEnvironment) => apiRequest<PlatformState>(`${base}/${environment}`);
export const getSpeechProfiles = () => apiRequest<{ profiles: SpeechProfile[]; message: string }>(`${base}/speech-profiles`);
export const updateComponent = (environment: VoiceEnvironment, component: VoiceComponent, version: number, enabled: boolean, profile_id: string | null, reason: string) => apiRequest<PlatformState>(`${base}/${environment}/components/${component}`, { method: "PUT", body: JSON.stringify({ version, enabled, profile_id, reason }) });
export const setActivation = (environment: VoiceEnvironment, data: { version: number; direction: "inbound" | "outbound" | "processing"; enabled: boolean; reason: string; confirmation?: string; evidence_token?: string }) => apiRequest<PlatformState>(`${base}/${environment}/activation`, { method: "POST", body: JSON.stringify(data) });
export const emergencyVoiceStop = (environment: VoiceEnvironment, reason: string) => apiRequest<PlatformState>(`${base}/${environment}/emergency`, { method: "POST", body: JSON.stringify({ reason }) });
export const getSpeechJobs = (environment: VoiceEnvironment, page: number) => apiRequest<{ items: SpeechJob[]; total: number }>(`${base}/${environment}/speech-tests?page=${page}`);
export const startSpeechTest = (environment: VoiceEnvironment, profile: string) => apiRequest<SpeechJob>(`${base}/${environment}/speech-tests/${profile}`, { method: "POST" });
export const startPipelineTest = (environment: VoiceEnvironment) => apiRequest<SpeechJob>(`${base}/${environment}/pipeline-tests`, { method: "POST" });
export const getSpeechTestAudio = (environment: VoiceEnvironment, id: string) => apiBlob(`${base}/${environment}/speech-tests/${id}/audio`);
