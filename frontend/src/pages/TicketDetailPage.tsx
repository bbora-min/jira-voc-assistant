import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getTicket } from "@/api/tickets";
import {
  approveTicket,
  listCategories,
  listJiraComments,
  patchDraft,
  reclassifyTicket,
  regenerateTicket,
  rejectTicket,
} from "@/api/actions";
import { TiptapEditor } from "@/components/editor/TiptapEditor";
import { useTicketEvents } from "@/hooks/useTicketEvents";
import type {
  ClassificationOut,
  DraftOut,
  ReferenceOut,
  TicketDetail,
} from "@/types/api";

function ConfidenceBar({ value }: { value: number }) {
  const color = value >= 80 ? "#2f9e44" : value >= 60 ? "#d97706" : "#d93b3b";
  return (
    <div className="conf-bar">
      <div className="conf-bar-fill" style={{ width: `${value}%`, background: color }} />
      <span className="conf-bar-text">{value}</span>
    </div>
  );
}

function ClassificationPanel({
  classification,
  ticketId,
  disabled,
}: {
  classification: ClassificationOut | null;
  ticketId: number;
  disabled: boolean;
}) {
  const qc = useQueryClient();
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: listCategories,
    staleTime: 5 * 60_000,
  });

  const reclassify = useMutation({
    mutationFn: (categoryId: number) => reclassifyTicket(ticketId, categoryId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ticket", ticketId] }),
  });

  if (!classification) {
    return (
      <div className="card panel">
        <h2>AI 분류</h2>
        <p className="muted">분류 결과 없음</p>
      </div>
    );
  }

  const selectedId =
    categories?.find((c) => c.code === classification.category_code)?.id ?? "";

  return (
    <div className="card panel">
      <h2>AI 분류</h2>
      <div className="meta-row">
        <span className="meta-label">카테고리</span>
        <span className="meta-value" style={{ flex: 1 }}>
          <select
            value={selectedId}
            disabled={disabled || reclassify.isPending}
            onChange={(e) => reclassify.mutate(Number(e.target.value))}
            className="select"
          >
            {categories?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label_ko}
              </option>
            ))}
          </select>
        </span>
      </div>
      <div className="meta-row">
        <span className="meta-label">AI 신뢰도</span>
        <span className="meta-value" style={{ flex: 1 }}>
          <ConfidenceBar value={classification.confidence} />
        </span>
      </div>
      {classification.was_corrected && (
        <div className="meta-row">
          <span className="meta-label">상태</span>
          <span className="status-pill warn">운영자 수정됨</span>
        </div>
      )}
      {reclassify.isPending && <p className="muted small">변경 중…</p>}
    </div>
  );
}

function ReferencesPanel({ refs }: { refs: ReferenceOut[] }) {
  if (refs.length === 0) {
    return (
      <div className="card panel">
        <h2>참고 문서</h2>
        <p className="muted">검색된 문서가 없습니다.</p>
      </div>
    );
  }
  return (
    <div className="card panel">
      <h2>참고 문서 ({refs.length})</h2>
      <ul className="ref-list">
        {refs.map((r, i) => (
          <li key={r.source_id + r.position} className="ref-item">
            <div className="ref-head">
              <span className="ref-num">[#{i + 1}]</span>
              <a href={r.source_url} target="_blank" rel="noreferrer" className="ref-title">
                {r.source_title}
              </a>
              <span className={`status-pill ${r.kind === "past_voc" ? "warn" : "ok"}`}>
                {r.kind === "past_voc" ? "과거 VOC" : "Confluence"}
              </span>
              <span className="ref-score">{r.score.toFixed(2)}</span>
            </div>
            {r.snippet && <p className="ref-snippet">{r.snippet}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DraftPanel({
  ticket,
  draft,
}: {
  ticket: TicketDetail;
  draft: DraftOut;
}) {
  const qc = useQueryClient();
  const [html, setHtml] = useState(draft.body_html_edited ?? draft.body_html);
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  useEffect(() => {
    const next = draft.body_html_edited ?? draft.body_html;
    setHtml(next);
    setDirty(false);
  }, [draft.id, draft.body_html, draft.body_html_edited]);

  const save = useMutation({
    mutationFn: () => patchDraft(ticket.id, html),
    onSuccess: () => {
      setDirty(false);
      setSavedAt(new Date().toLocaleTimeString("ko-KR"));
    },
  });
  const approve = useMutation({
    mutationFn: async () => {
      if (dirty) await patchDraft(ticket.id, html);
      return approveTicket(ticket.id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ticket", ticket.id] });
      qc.invalidateQueries({ queryKey: ["jira-comments", ticket.id] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
    },
  });
  const reject = useMutation({
    mutationFn: () => rejectTicket(ticket.id, rejectReason || "(사유 미기재)", html),
    onSuccess: () => {
      setRejectOpen(false);
      setRejectReason("");
      qc.invalidateQueries({ queryKey: ["ticket", ticket.id] });
      qc.invalidateQueries({ queryKey: ["jira-comments", ticket.id] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
    },
  });
  const regenerate = useMutation({
    mutationFn: () => regenerateTicket(ticket.id),
  });

  const completed = ticket.status === "DONE" || ticket.status === "REJECTED";

  return (
    <div className="card panel">
      <div className="panel-header">
        <h2>AI 초안</h2>
        <span className="muted small">
          {draft.model} · {draft.generation_ms ?? "-"}ms · conf {draft.confidence}
        </span>
      </div>

      <TiptapEditor
        initialHtml={html}
        onChange={(h) => {
          setHtml(h);
          setDirty(true);
        }}
        disabled={completed}
      />

      {!completed && (
        <div className="action-row">
          <button
            type="button"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "저장 중…" : dirty ? "초안 저장" : savedAt ? `저장됨 (${savedAt})` : "저장됨"}
          </button>
          <button
            type="button"
            disabled={regenerate.isPending}
            onClick={() => regenerate.mutate()}
          >
            {regenerate.isPending ? "재생성 중…" : "↻ 재생성"}
          </button>
          <button
            type="button"
            disabled={reject.isPending}
            onClick={() => setRejectOpen(true)}
            title="AI 초안을 채택하지 않고 직접 작성한 답변을 등록 (사유는 LLM 학습용)"
          >
            ✎ 수정 후 등록
          </button>
          <button
            type="button"
            className="primary"
            disabled={approve.isPending}
            onClick={() => approve.mutate()}
          >
            {approve.isPending ? "승인 중…" : "✓ 승인 & Jira 코멘트 등록"}
          </button>
        </div>
      )}

      {completed && (
        <p className="muted small" style={{ marginTop: 8 }}>
          처리 완료 — 상태: <strong>{ticket.status}</strong>
          {ticket.completed_at && ` · ${new Date(ticket.completed_at).toLocaleString("ko-KR")}`}
        </p>
      )}

      {approve.isError && (
        <div className="banner err">승인 실패: {(approve.error as Error).message}</div>
      )}
      {approve.data && (
        <div className="banner ok">
          승인 완료 — Jira 코멘트 ID:{" "}
          <span className="mono small">{approve.data.comment_id}</span> · 수정 거리:{" "}
          {approve.data.edit_distance}
        </div>
      )}
      {reject.isError && (
        <div className="banner err">등록 실패: {(reject.error as Error).message}</div>
      )}
      {reject.data && (
        <div className="banner ok">
          미채택 사유 기록 + 직접 작성본 Jira 등록 완료 — 코멘트 ID:{" "}
          <span className="mono small">{reject.data.comment_id}</span> · 수정 거리:{" "}
          {reject.data.edit_distance}
        </div>
      )}

      {rejectOpen && (
        <div className="modal-overlay" onClick={() => setRejectOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>AI 초안을 채택하지 않은 이유</h3>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="어떤 점이 부적절했나요? (LLM 재학습용 negative feedback 으로 보존됩니다)"
              rows={4}
            />
            <p className="muted small">
              현재 편집창의 본문이 그대로 Jira 코멘트로 등록되며, 위 사유는 LLM 학습 데이터로 보존됩니다.
            </p>
            <div className="action-row">
              <button type="button" onClick={() => setRejectOpen(false)}>취소</button>
              <button
                type="button"
                className="primary"
                disabled={!rejectReason.trim() || reject.isPending}
                onClick={() => reject.mutate()}
              >
                {reject.isPending ? "처리 중…" : "사유 기록 후 Jira 등록"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function JiraCommentsPanel({ ticketId, status }: { ticketId: number; status: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["jira-comments", ticketId],
    queryFn: () => listJiraComments(ticketId),
    enabled: status === "DONE",
  });
  if (status !== "DONE") return null;
  return (
    <div className="card">
      <h2>Mock Jira 코멘트</h2>
      {isLoading && <p className="muted">불러오는 중…</p>}
      {data?.length === 0 && <p className="muted">등록된 코멘트가 없습니다.</p>}
      {data?.map((c) => (
        <div key={c.id} className="jira-comment">
          <div className="meta-row">
            <span className="meta-label">코멘트 ID</span>
            <span className="meta-value mono">{c.id}</span>
            <span className="meta-value muted small">
              {new Date(c.posted_at).toLocaleString("ko-KR")}
            </span>
          </div>
          <div
            className="draft-body"
            dangerouslySetInnerHTML={{ __html: c.body_html }}
          />
        </div>
      ))}
    </div>
  );
}

export function TicketDetailPage() {
  useTicketEvents();
  const { id } = useParams();
  const ticketId = Number(id);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ticket", ticketId],
    queryFn: () => getTicket(ticketId),
    enabled: Number.isFinite(ticketId),
    refetchOnMount: "always",
  });

  return (
    <div>
      <div className="page-header">
        <h1>티켓 상세</h1>
        <Link to="/tickets" className="back-link">
          ← 목록으로
        </Link>
      </div>

      {isLoading && <div className="card">불러오는 중…</div>}
      {isError && <div className="card err">에러: {(error as Error).message}</div>}

      {data && (
        <>
          <div className="card">
            <div className="meta-row">
              <span className="meta-label">Jira Key</span>
              <span className="meta-value mono">{data.jira_key}</span>
              <span className="status-pill">{data.status}</span>
            </div>
            <div className="meta-row">
              <span className="meta-label">접수 시각</span>
              <span className="meta-value">
                {new Date(data.received_at).toLocaleString("ko-KR")}
              </span>
            </div>
            <div className="meta-row">
              <span className="meta-label">담당자 / 신고자</span>
              <span className="meta-value">
                {data.assignee ?? "-"} / {data.reporter ?? "-"}
              </span>
            </div>
          </div>

          <div className="card">
            <h2>제목</h2>
            <p style={{ margin: 0 }}>{data.title}</p>
          </div>

          <div className="card">
            <h2>본문</h2>
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 13, margin: 0 }}>
              {data.body || "(본문 없음)"}
            </pre>
          </div>

          <div className="phase5-grid">
            <ClassificationPanel
              classification={data.classification}
              ticketId={data.id}
              disabled={data.status === "DONE" || data.status === "REJECTED"}
            />
            {data.draft ? (
              <DraftPanel ticket={data} draft={data.draft} />
            ) : (
              <div className="card panel">
                <h2>AI 초안</h2>
                <p className="muted">초안이 아직 생성되지 않았습니다.</p>
              </div>
            )}
            <ReferencesPanel refs={data.references} />
          </div>

          <JiraCommentsPanel ticketId={data.id} status={data.status} />
        </>
      )}
    </div>
  );
}
