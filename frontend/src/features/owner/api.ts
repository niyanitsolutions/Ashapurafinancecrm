import type { LoginResponse } from "@/features/auth/api";
import { apiRequest } from "@/shared/api/client";

export interface RegistrationStatus {
  owner_exists: boolean;
}

export interface RegisterOwnerInput {
  company_name: string;
  owner_name: string;
  mobile: string;
  email: string;
  password: string;
  accept_terms: boolean;
}

export function getRegistrationStatus() {
  return apiRequest<RegistrationStatus>("/owner/registration-status");
}

export function registerOwner(payload: RegisterOwnerInput) {
  return apiRequest<LoginResponse>("/owner/register", { method: "POST", body: JSON.stringify(payload) });
}
