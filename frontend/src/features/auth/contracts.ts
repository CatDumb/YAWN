export type Membership = {
  company: string;
  company_id: number;
  role: string;
};

export type CurrentUser = {
  email: string;
  first_name: string;
  id: number;
  last_name: string;
  memberships: Membership[];
};

export function isCurrentUser(value: unknown): value is CurrentUser {
  return (
    typeof value === "object" &&
    value !== null &&
    "email" in value &&
    typeof value.email === "string" &&
    "memberships" in value &&
    Array.isArray(value.memberships)
  );
}
