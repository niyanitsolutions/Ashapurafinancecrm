import { apiRequest } from "@/shared/api/client";
import type { LoginResponse } from "./api";
export type Purpose = "FIRST_TIME_LOGIN" | "FORGOT_PIN" | "REGISTRATION";
export interface Challenge {
  challenge_id: string;
  masked_mobile: string;
  expires_in: number;
  resend_after: number;
  message: string;
}
const post = <T,>(path: string, body: unknown) => apiRequest<T>(`/auth/pin/${path}`, { method: "POST", body: JSON.stringify(body) });
export const pinPolicy = () => apiRequest<{
  mode: "enrollment" | "pin_only";
}>("/auth/pin/policy");
export const startPin = (mobile: string, purpose: Purpose) => post<Challenge>("start", { mobile, purpose });
export const verifyPinOtp = (mobile: string, purpose: Purpose, challenge_id: string, otp: string) => post<{
  authorization: string;
  next_action?: "login" | "register" | "set_pin";
}>("verify", { mobile, purpose, challenge_id, otp });
export const finishPin = (authorization: string, pin: string, confirm_pin: string, coordinates: {
  latitude: number;
  longitude: number;
} | null) => post<LoginResponse | {
  message: string;
}>("complete", { authorization, pin, confirm_pin, ...coordinates });
export const loginPin = (mobile: string, pin: string, coordinates: {
  latitude: number;
  longitude: number;
} | null) => post<LoginResponse>("login", { mobile, pin, ...coordinates });
