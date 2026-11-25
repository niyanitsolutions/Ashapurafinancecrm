import { z } from "zod";

export const directRegisterSchema = z.object({
  full_name: z.string().trim().min(2, "Enter your full name").max(200),
  terms_accepted: z.boolean().refine(value => value, "Accept the applicable terms to continue"),
  mobile: z.string().regex(/^[0-9]{10}$/, "Enter exactly 10 digits"),
  email: z.union([z.literal(""), z.string().email("Enter a valid email")]).optional(),
  pin: z.string().regex(/^[0-9]{4}$/, "Enter exactly 4 numeric digits"),
  confirm_pin: z.string().regex(/^[0-9]{4}$/, "Enter exactly 4 numeric digits"),
}).refine(data => data.pin === data.confirm_pin, {
  message: "PIN confirmation does not match", path: ["confirm_pin"],
});
export type DirectRegisterFormValues = z.infer<typeof directRegisterSchema>;
