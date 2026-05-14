import { api } from "./client";

export interface Category {
  id: number;
  code: string;
  label_ko: string;
  label_en: string | null;
}

export async function listCategories(): Promise<Category[]> {
  const res = await api.get<{ items: Category[] }>("/api/categories");
  return res.data.items;
}

export async function patchDraft(ticketId: number, body_html_edited: string) {
  const res = await api.patch(`/api/tickets/${ticketId}/draft`, { body_html_edited });
  return res.data;
}

export async function approveTicket(ticketId: number): Promise<{
  ok: boolean;
  status: string;
  comment_id: string;
  edit_distance: number;
}> {
  const res = await api.post(`/api/tickets/${ticketId}/approve`);
  return res.data;
}

export async function rejectTicket(
  ticketId: number,
  reason: string,
  manual_body_html?: string
): Promise<{
  ok: boolean;
  status: string;
  comment_id: string;
  edit_distance: number;
  not_adopted: boolean;
}> {
  const res = await api.post(`/api/tickets/${ticketId}/reject`, {
    reason,
    manual_body_html,
  });
  return res.data;
}

export async function reclassifyTicket(
  ticketId: number,
  category_id: number
): Promise<{ ok: boolean; changed: boolean; to?: string }> {
  const res = await api.post(`/api/tickets/${ticketId}/reclassify`, { category_id });
  return res.data;
}

export async function regenerateTicket(
  ticketId: number
): Promise<{ ok: boolean; queued: boolean }> {
  const res = await api.post(`/api/tickets/${ticketId}/regenerate`);
  return res.data;
}

export interface JiraComment {
  id: string;
  body_html: string;
  posted_at: string;
}

export async function listJiraComments(ticketId: number): Promise<JiraComment[]> {
  const res = await api.get<{ items: JiraComment[] }>(
    `/api/tickets/${ticketId}/jira-comments`
  );
  return res.data.items;
}

export async function uploadImage(
  file: File
): Promise<{ id: number; url: string; filename: string; mime: string; size: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post("/api/uploads", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}
