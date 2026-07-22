import { z } from "zod";

export const accessRequestSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  first_name: z.string().trim().min(1, "Enter your first name.").max(150),
  last_name: z.string().trim().min(1, "Enter your last name.").max(150),
});

export const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
});

export type AccessRequestValues = z.infer<typeof accessRequestSchema>;
export type LoginValues = z.infer<typeof loginSchema>;
