import { z } from "zod";
import { mobileSchema, passwordSchema } from "@/features/auth/validation";

// Mirrors backend/app/features/customer/schemas.py:CompleteDirectRegistrationRequest —
// the one Customer self-registration form (Owner/Employee/Referral Partner are always
// staff-created, never self-registered).
export const directRegisterSchema = z
  .object({
    full_name: z.string().min(3, "Full name must be at least 3 characters"),
    email: z.string().email("Enter a valid email"),
    mobile: mobileSchema,
    password: passwordSchema,
    confirm_password: z.string(),
    address_line1: z.string().min(1, "Address is required"),
    city: z.string().min(1, "City is required"),
    state: z.string().min(1, "State is required"),
    pincode: z.string().regex(/^\d{6}$/, "Enter a valid 6-digit PIN code"),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

export type DirectRegisterFormValues = z.infer<typeof directRegisterSchema>;
