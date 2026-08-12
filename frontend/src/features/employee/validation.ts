import { z } from "zod";

const mobileSchema = z.string().regex(/^[6-9]\d{9}$/, "Enter a valid 10-digit mobile number");
const passwordSchema = z.string().min(8, "Must be at least 8 characters").max(72);

const addressSchema = z.object({
  line1: z.string().min(1, "Required"),
  line2: z.string().optional(),
  city: z.string().min(1, "Required"),
  state: z.string().min(1, "Required"),
  pincode: z.string().min(1, "Required"),
  country: z.string().default("India"),
});

const emergencyContactSchema = z.object({
  name: z.string().min(1, "Required"),
  relationship: z.string().min(1, "Required"),
  mobile: mobileSchema,
});

const bankDetailsSchema = z.object({
  account_holder_name: z.string().min(1, "Required"),
  bank_name: z.string().min(1, "Required"),
  branch_name: z.string().min(1, "Required"),
  ifsc_code: z.string().min(1, "Required"),
  account_number: z.string().min(4, "Required"),
});

export const createEmployeeSchema = z.object({
  mobile: mobileSchema,
  initial_password: passwordSchema,
  first_name: z.string().min(1, "Required"),
  last_name: z.string().min(1, "Required"),
  display_name: z.string().optional(),
  gender: z.enum(["male", "female", "other"]).optional(),
  date_of_birth: z.string().optional(),
  blood_group: z.string().optional(),
  alternative_mobile: z.union([mobileSchema, z.literal("")]).optional(),
  email: z.string().email("Enter a valid email"),
  emergency_contact: emergencyContactSchema.optional(),
  current_address: addressSchema.optional(),
  permanent_address: addressSchema.optional(),
  department_id: z.string().min(1, "Required"),
  designation_id: z.string().min(1, "Required"),
  branch_id: z.string().min(1, "Required"),
  joining_date: z.string().min(1, "Required"),
  employment_type: z.enum(["full_time", "part_time", "contract", "intern"]),
  reporting_manager_id: z.string().optional(),
  bank_details: bankDetailsSchema.optional(),
});
export type CreateEmployeeFormValues = z.infer<typeof createEmployeeSchema>;

// Simplified Add Employee form — only what HR actually needs to get someone started.
// joining_date/employment_type are backend-required but not asked here; the Create page
// silently defaults them (today / full_time) and they're editable afterward from the
// Employee Profile's Employment tab, per the "quick add, detail later" redesign.
export const simpleCreateEmployeeSchema = z.object({
  first_name: z.string().min(1, "Required"),
  last_name: z.string().min(1, "Required"),
  email: z.string().email("Enter a valid email"),
  mobile: mobileSchema,
  initial_password: passwordSchema,
  department_id: z.string().min(1, "Required"),
  designation_id: z.string().min(1, "Required"),
  branch_id: z.string().min(1, "Required"),
  reporting_manager_id: z.string().optional(),
});
export type SimpleCreateEmployeeFormValues = z.infer<typeof simpleCreateEmployeeSchema>;

export const updateEmployeeSchema = createEmployeeSchema
  .omit({ mobile: true, initial_password: true })
  .partial()
  .extend({ status: z.enum(["active", "inactive", "suspended", "on_leave", "resigned"]).optional() });
export type UpdateEmployeeFormValues = z.infer<typeof updateEmployeeSchema>;

export const selfUpdateEmployeeSchema = z.object({
  first_name: z.string().min(1, "Required").optional(),
  last_name: z.string().min(1, "Required").optional(),
  display_name: z.string().optional(),
  gender: z.enum(["male", "female", "other"]).optional(),
  date_of_birth: z.string().optional(),
  blood_group: z.string().optional(),
  alternative_mobile: z.union([mobileSchema, z.literal("")]).optional(),
  emergency_contact: emergencyContactSchema.optional(),
  current_address: addressSchema.optional(),
  permanent_address: addressSchema.optional(),
});
export type SelfUpdateEmployeeFormValues = z.infer<typeof selfUpdateEmployeeSchema>;
