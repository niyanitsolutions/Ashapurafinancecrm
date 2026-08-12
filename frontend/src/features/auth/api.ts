// Typed calls for the auth endpoints the frontend uses. Module 2 added `getProfile`,
// needed to resolve role/user_id after a silent refresh-on-load (see
// features/auth/context.tsx). `changePassword` was added later for the Profile menu's
// "Change Password" page — the backend endpoint always existed, it just had no UI yet.
import { apiRequest } from "@/shared/api/client";

export interface GenericOtpSentResponse {
  message: string;
  dev_otp: string | null;
}

export interface VerifyOtpResponse {
  otp_verified_token: string;
  is_new_user: boolean;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  role: string;
  user_id: string;
  must_change_password: boolean;
}

export interface TokenPairResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface ProfileResponse {
  user_id: string;
  mobile: string;
  role: string;
  status: string;
  is_mobile_verified: boolean;
  must_change_password: boolean;
  created_at: string;
}

export type OtpPurpose = "signup" | "forgot_password";
export type SelfSignupRole = "customer" | "referral_partner";

export function getProfile() {
  return apiRequest<ProfileResponse>("/auth/profile");
}

export function sendOtp(mobile: string, role: SelfSignupRole) {
  return apiRequest<GenericOtpSentResponse>("/auth/send-otp", {
    method: "POST",
    body: JSON.stringify({ mobile, role }),
  });
}

export function forgotPassword(mobile: string) {
  return apiRequest<GenericOtpSentResponse>("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ mobile }),
  });
}

export function verifyOtp(mobile: string, otp: string, purpose: OtpPurpose) {
  return apiRequest<VerifyOtpResponse>("/auth/verify-otp", {
    method: "POST",
    body: JSON.stringify({ mobile, otp, purpose }),
  });
}

export function resetPassword(otpVerifiedToken: string, newPassword: string) {
  return apiRequest<null>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ otp_verified_token: otpVerifiedToken, new_password: newPassword }),
  });
}

export function login(mobile: string, password: string) {
  return apiRequest<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ mobile, password }),
  });
}

export function changePassword(currentPassword: string, newPassword: string) {
  return apiRequest<null>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export function refreshTokens(refreshToken: string) {
  return apiRequest<TokenPairResponse>("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

// ---- self-service session management (every role) ----

export interface SessionSummary {
  id: string;
  device: string | null;
  browser: string | null;
  operating_system: string | null;
  ip_address: string | null;
  city: string | null;
  country: string | null;
  login_at: string;
  last_activity_at: string;
  status: string;
}

export function getOwnSessions() {
  return apiRequest<SessionSummary[]>("/auth/sessions");
}

export function revokeSession(sessionId: string) {
  return apiRequest<null>(`/auth/sessions/${sessionId}/revoke`, { method: "POST" });
}

export function logoutAllOtherSessions(refreshToken: string | null) {
  return apiRequest<{ revoked_count: number }>("/auth/logout-all", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}
