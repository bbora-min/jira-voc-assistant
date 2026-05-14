export type UserRole = "ADMIN" | "OPERATOR";

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
}

export type TicketStatus = "PENDING" | "IN_PROGRESS" | "DONE" | "REJECTED";
export type CategoryCode = "SYSTEM_ISSUE" | "FEATURE_INQUIRY" | "FEATURE_REQUEST";

export interface HealthResponse {
  status: string;
  integration_mode: string;
  draft_model: string;
  classify_model: string;
}

export interface TicketSummary {
  id: number;
  jira_key: string;
  title: string;
  status: TicketStatus;
  assignee: string | null;
  received_at: string;
  completed_at: string | null;
  not_adopted: boolean;
}

export interface ClassificationOut {
  category_code: string | null;
  category_label: string | null;
  predicted_category_code: string | null;
  confidence: number;
  was_corrected: boolean;
}

export interface DraftOut {
  id: number;
  body_html: string;
  body_html_edited: string | null;
  confidence: number;
  model: string;
  generation_ms: number | null;
}

export interface ReferenceOut {
  source_id: string;
  source_title: string;
  source_url: string;
  kind: string;
  snippet: string | null;
  score: number;
  position: number;
}

export interface TicketDetail extends TicketSummary {
  body: string | null;
  reporter: string | null;
  attachments: unknown[] | null;
  classification: ClassificationOut | null;
  draft: DraftOut | null;
  references: ReferenceOut[];
}

export interface TicketListResponse {
  items: TicketSummary[];
  total: number;
  counts: Record<TicketStatus, number>;
}

export interface WSEvent<T = unknown> {
  type: string;
  id?: string;
  payload?: T;
  ts?: number;
}
