import { api } from "./client";

export interface AdminCategory {
  id: number;
  code: string;
  label_ko: string;
  label_en: string | null;
  sort_order: number;
  is_active: boolean;
}

export async function listAdminCategories(): Promise<AdminCategory[]> {
  const res = await api.get<AdminCategory[]>("/api/admin/categories");
  return res.data;
}

export async function createCategory(payload: {
  code: string;
  label_ko: string;
  label_en?: string;
  sort_order?: number;
}): Promise<AdminCategory> {
  const res = await api.post<AdminCategory>("/api/admin/categories", payload);
  return res.data;
}

export async function updateCategory(
  id: number,
  payload: Partial<Pick<AdminCategory, "label_ko" | "label_en" | "sort_order" | "is_active">>
): Promise<AdminCategory> {
  const res = await api.patch<AdminCategory>(`/api/admin/categories/${id}`, payload);
  return res.data;
}

export async function deactivateCategory(id: number): Promise<void> {
  await api.delete(`/api/admin/categories/${id}`);
}

// ─── 프롬프트 템플릿 버전 관리 ───

export type PromptKind = "CLASSIFY" | "DRAFT";

export interface PromptTemplateOut {
  id: number;
  kind: PromptKind;
  version: number;
  content: string;
  is_active: boolean;
  note: string | null;
  created_at: string | null;
}

export async function listPrompts(kind?: PromptKind): Promise<PromptTemplateOut[]> {
  const res = await api.get<PromptTemplateOut[]>("/api/admin/prompts", {
    params: kind ? { kind } : {},
  });
  return res.data;
}

export async function createPrompt(payload: {
  kind: PromptKind;
  content: string;
  note?: string;
  activate?: boolean;
}): Promise<PromptTemplateOut> {
  const res = await api.post<PromptTemplateOut>("/api/admin/prompts", payload);
  return res.data;
}

export async function activatePrompt(id: number): Promise<PromptTemplateOut> {
  const res = await api.post<PromptTemplateOut>(`/api/admin/prompts/${id}/activate`);
  return res.data;
}

export async function previewPrompt(payload: {
  kind: PromptKind;
  content: string;
}): Promise<{ ok: boolean; rendered?: string; error?: string }> {
  const res = await api.post("/api/admin/prompts/preview", payload);
  return res.data;
}
