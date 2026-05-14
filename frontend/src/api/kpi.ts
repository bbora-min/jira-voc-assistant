import { api } from "./client";

export interface KpiCard {
  value: number;
  num?: number;
  den?: number;
  samples?: number;
}

export interface KpiSummary {
  period: { from: string; to: string; group_by: string };
  cards: {
    adoption_rate: KpiCard;
    classification_accuracy: KpiCard;
    avg_edit_distance: KpiCard;
    avg_response_ms: KpiCard;
  };
  counts: {
    DRAFT_GENERATED: number;
    DRAFT_APPROVED: number;
    DRAFT_REJECTED: number;
    CLASSIFICATION_CORRECTED: number;
  };
  series: Array<{
    bucket: string;
    generated: number;
    approved: number;
    rejected: number;
    corrected: number;
    adoption_rate: number;
    classification_accuracy: number | null;
    avg_response_ms: number | null;
    avg_edit_distance: number | null;
  }>;
}

export interface RejectionReasons {
  period: { from: string; to: string };
  total: number;
  top_keywords: Array<{ keyword: string; count: number }>;
  items: Array<{
    ticket_id: number;
    jira_key: string;
    ticket_title: string;
    reason: string;
    edit_distance: number | null;
    created_at: string | null;
  }>;
}

export async function getKpiSummary(params: { from?: string; to?: string; group_by?: "day" | "week" } = {}): Promise<KpiSummary> {
  const res = await api.get<KpiSummary>("/api/kpi/summary", { params });
  return res.data;
}

export async function getRejectionReasons(params: { from?: string; to?: string; limit?: number } = {}): Promise<RejectionReasons> {
  const res = await api.get<RejectionReasons>("/api/kpi/rejection-reasons", { params });
  return res.data;
}
