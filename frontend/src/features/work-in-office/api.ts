import { apiFetch } from "../../lib/api";
import { apiErrorFromResponse } from "../../lib/errors";

export type WorkInOfficeRecord = {
  id: number;
  work_date: string;
  location_choice: "in_office" | "not_in_office" | null;
  review_state:
    | "draft"
    | "pending"
    | "pending_assignment"
    | "approved"
    | "rejected"
    | "not_required"
    | "expired_pending";
  note: string;
  approver_note: string;
  version: number;
  created_at: string;
  updated_at: string;
  rejected_at?: string | null;
  correction_deadline?: string | null;
  approved_at?: string | null;
  approval_method?: "manager_approved" | "self_approved" | null;
};

export type WorkInOfficeAuditEvent = {
  event_type: string;
  metadata: Record<string, string | null>;
  created_at: string;
};

export type WorkInOfficeRecordDetail = WorkInOfficeRecord & {
  audit_timeline: WorkInOfficeAuditEvent[];
};

export type WorkInOfficeMetadata = {
  company_date: string;
  timezone: string;
};

export type WorkInOfficeInput = {
  work_date: string;
  location_choice?: WorkInOfficeRecord["location_choice"];
  note?: string;
  version?: number;
};

async function read<T>(response: Response, fallbackDetail: string): Promise<T> {
  if (!response.ok) throw await apiErrorFromResponse(response, fallbackDetail);
  return response.json() as Promise<T>;
}

export async function listWorkInOffice(params: string, fallbackDetail: string) {
  return read<WorkInOfficeRecord[]>(
    await apiFetch(`/api/v1/work-in-office/${params}`),
    fallbackDetail,
  );
}

export async function getWorkInOffice(id: string, fallbackDetail: string) {
  return read<WorkInOfficeRecordDetail>(
    await apiFetch(`/api/v1/work-in-office/${id}/`),
    fallbackDetail,
  );
}

export async function getWorkInOfficeMetadata(fallbackDetail: string) {
  return read<WorkInOfficeMetadata>(
    await apiFetch("/api/v1/work-in-office/meta/"),
    fallbackDetail,
  );
}

export async function saveWorkInOffice(
  input: WorkInOfficeInput,
  id: string | undefined,
  fallbackDetail: string,
) {
  return read<WorkInOfficeRecord>(
    await apiFetch(`/api/v1/work-in-office/${id ? `${id}/` : ""}`, {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(input),
    }),
    fallbackDetail,
  );
}

export async function deleteWorkInOffice(
  id: string,
  version: number,
  fallbackDetail: string,
) {
  const response = await apiFetch(
    `/api/v1/work-in-office/${id}/?version=${version}`,
    {
      method: "DELETE",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    },
  );
  if (!response.ok) return read<never>(response, fallbackDetail);
}

export async function undoSelfApproval(
  id: number,
  version: number,
  fallbackDetail: string,
) {
  return read<WorkInOfficeRecord>(
    await apiFetch(`/api/v1/work-in-office/${id}/undo-self-approval/`, {
      method: "POST",
      body: JSON.stringify({ version }),
    }),
    fallbackDetail,
  );
}
