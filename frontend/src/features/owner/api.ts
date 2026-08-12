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

// ---------------------------------------------------------------------- owner account management

export interface OwnerAccountListItem {
  id: string;
  full_name: string;
  mobile: string;
  email: string;
  owner_type: "primary" | "secondary";
  status: string;
  created_at: string;
}

export interface OwnerAccountDetail extends OwnerAccountListItem {
  user_id: string;
  updated_at: string;
}

export interface CreateSecondaryOwnerInput {
  full_name: string;
  mobile: string;
  email: string;
  initial_password: string;
}

export interface UpdateSecondaryOwnerInput {
  full_name?: string;
  email?: string;
}

// Any authenticated Owner (Primary or Secondary) — used to tell the two apart, since
// useAuth().role is always just "owner" for both.
export function getOwnOwnerAccount() {
  return apiRequest<OwnerAccountDetail>("/owner/me");
}

// Everything below is Primary-Owner-only server-side (see require_primary_owner) —
// a Secondary Owner calling any of these gets a 403, regardless of frontend routing.

export function listOwnerAccounts() {
  return apiRequest<OwnerAccountListItem[]>("/owner/accounts");
}

export function getOwnerAccount(ownerProfileId: string) {
  return apiRequest<OwnerAccountDetail>(`/owner/accounts/${ownerProfileId}`);
}

export function createSecondaryOwner(payload: CreateSecondaryOwnerInput) {
  return apiRequest<OwnerAccountDetail>("/owner/accounts", { method: "POST", body: JSON.stringify(payload) });
}

export function updateSecondaryOwner(ownerProfileId: string, payload: UpdateSecondaryOwnerInput) {
  return apiRequest<OwnerAccountDetail>(`/owner/accounts/${ownerProfileId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deactivateSecondaryOwner(ownerProfileId: string) {
  return apiRequest<OwnerAccountDetail>(`/owner/accounts/${ownerProfileId}/deactivate`, { method: "PATCH" });
}

export function activateSecondaryOwner(ownerProfileId: string) {
  return apiRequest<OwnerAccountDetail>(`/owner/accounts/${ownerProfileId}/activate`, { method: "PATCH" });
}
