import { Link } from "react-router-dom";
import type { TicketSummary } from "@/types/api";

const statusLabel: Record<TicketSummary["status"], string> = {
  PENDING: "대기",
  IN_PROGRESS: "처리 중",
  DONE: "완료",
  REJECTED: "거부",
};

const statusClass: Record<TicketSummary["status"], string> = {
  PENDING: "warn",
  IN_PROGRESS: "ok",
  DONE: "ok",
  REJECTED: "err",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function TicketRow({ t }: { t: TicketSummary }) {
  const isDone = t.status === "DONE";
  return (
    <Link to={`/tickets/${t.id}`} className="ticket-row">
      <div className="ticket-row-key">{t.jira_key}</div>
      <div className="ticket-row-title">
        {t.title}
        {isDone && t.not_adopted && (
          <span className="adopt-badge not-adopted" title="운영자가 AI 초안을 채택하지 않고 직접 작성한 답변을 등록한 케이스. LLM 학습용 negative feedback 보존됨.">
            직접 작성
          </span>
        )}
        {isDone && !t.not_adopted && (
          <span className="adopt-badge adopted" title="AI 초안을 그대로 또는 가볍게 수정해서 등록한 케이스">
            AI 채택
          </span>
        )}
      </div>
      <div>
        <span className={`status-pill ${statusClass[t.status]}`}>{statusLabel[t.status]}</span>
      </div>
      <div className="ticket-row-meta">{formatDate(t.received_at)}</div>
    </Link>
  );
}
