import { api } from "./client";
import type { TicketDetail, TicketListResponse, TicketStatus } from "@/types/api";

export interface ListParams {
  status?: TicketStatus;
  limit?: number;
  offset?: number;
}

export async function listTickets(params: ListParams = {}): Promise<TicketListResponse> {
  const res = await api.get<TicketListResponse>("/api/tickets", { params });
  return res.data;
}

export async function getTicket(id: number): Promise<TicketDetail> {
  const res = await api.get<TicketDetail>(`/api/tickets/${id}`);
  return res.data;
}

export async function listSampleWebhooks(): Promise<{ items: string[] }> {
  const res = await api.get<{ items: string[] }>("/api/dev/sample-webhooks");
  return res.data;
}

export async function injectSample(name: string): Promise<{ ok: boolean; jira_key: string }> {
  const res = await api.post(`/api/dev/inject-webhook/${name}`);
  return res.data;
}

export async function injectRandom(): Promise<{ ok: boolean; jira_key: string; sample: string }> {
  const res = await api.post("/api/dev/inject-random");
  return res.data;
}
