import { z } from "zod";
import { mobileSchema, passwordSchema } from "@/features/auth/validation";

export const ownerRegisterSchema = z
  .object({
    company_name: z.string().min(1, "Company name is required"),
    owner_name: z.string().min(1, "Owner name is required"),
    mobile: mobileSchema,
    email: z.string().email("Enter a valid email address"),
    password: passwordSchema,
    confirm_password: z.string(),
    accept_terms: z.literal(true, { message: "You must accept the Terms & Conditions" }),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

export type OwnerRegisterFormValues = z.infer<typeof ownerRegisterSchema>;
