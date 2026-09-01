import type { ExaminationOutcome, RecruitmentStage } from "@/features/recruitment/api";

const titleCase = (value: string) =>
  value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");

export const GENDER_LABELS: Record<string, string> = { male: "Male", female: "Female", other: "Other" };

export const PROFESSION_LABELS: Record<string, string> = {
  house_wife: "House Wife",
  retired: "Retired",
  self_employed: "Self Employed",
  salaried: "Salaried",
  other: "Other",
};

export const NOMINEE_RELATIONSHIP_LABELS: Record<string, string> = {
  spouse: "Spouse",
  father: "Father",
  mother: "Mother",
  son: "Son",
  daughter: "Daughter",
  brother: "Brother",
  sister: "Sister",
  other: "Other",
};

export const STAGE_LABELS: Record<RecruitmentStage, string> = {
  fresh: "Fresh Leads",
  bop: "BOP",
  doc_collection_examination: "Document Collection — Examination",
  doc_collection_re_examination: "Document Collection — Re-Examination",
  advisor: "Advisor",
  rejected: "Rejected",
};

export const EXAM_LABELS: Record<ExaminationOutcome, string> = { pass: "PASS", fail: "FAIL", absent: "ABSENT" };

export const ADVISOR_PRODUCT_CATEGORY_LABELS: Record<string, string> = {
  savings: "Savings",
  protection: "Protection",
  ulip: "ULIP",
  annuity: "Annuity",
  business_insurance: "Business Insurance",
  custom: "Custom",
};

export const ADVISOR_CHANNEL_LABELS: Record<string, string> = { qr: "QR", non_qr: "Non QR" };
export const ADVISOR_STATUS_LABELS: Record<string, string> = { active: "Active", inactive: "Inactive" };

export function businessCategoryLabel(category: string, customCategory: string | null): string {
  if (category === "custom") return customCategory?.trim() || "Custom";
  return ADVISOR_PRODUCT_CATEGORY_LABELS[category] ?? category;
}

export function formatINR(amount: number): string {
  return `₹${amount.toLocaleString("en-IN")}`;
}

export function professionLabel(profession: string, otherProfession: string | null): string {
  if (profession === "other") return otherProfession?.trim() || "Other";
  return PROFESSION_LABELS[profession] ?? titleCase(profession);
}

export function activityLabel(eventType: string | null): string {
  if (!eventType) return "Activity";
  const map: Record<string, string> = {
    created: "Lead created",
    updated: "Details updated",
    moved_to_bop: "Moved to BOP",
    back_to_fresh: "Moved back to Fresh",
    moved_to_doc_collection: "Moved to Document Collection",
    documents_saved: "Documents saved",
    examination_recorded: "Examination recorded",
    moved_to_advisor: "Promoted to Advisor",
    rejected: "Rejected",
    assigned: "Assigned",
    note_added: "Note added",
  };
  return map[eventType] ?? titleCase(eventType);
}
