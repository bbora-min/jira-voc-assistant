import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  activatePrompt,
  createPrompt,
  listPrompts,
  previewPrompt,
  type PromptKind,
  type PromptTemplateOut,
} from "@/api/admin";
import { EmptyView, ErrorView, LoadingView } from "@/components/feedback/StateView";

export function AdminPromptsPage() {
  const [kind, setKind] = useState<PromptKind>("CLASSIFY");
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin-prompts", kind],
    queryFn: () => listPrompts(kind),
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-prompts", kind] });

  return (
    <div>
      <div className="page-header">
        <h1>관리 · 프롬프트 템플릿</h1>
        <span className="muted small">
          활성화된 버전이 즉시 다음 LLM 호출(분류/초안 생성)에 반영됩니다.
        </span>
      </div>

      <div className="card" style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <strong>종류:</strong>
        {(["CLASSIFY", "DRAFT"] as const).map((k) => (
          <button
            key={k}
            type="button"
            className={k === kind ? "primary" : ""}
            onClick={() => setKind(k)}
          >
            {k}
          </button>
        ))}
        <div style={{ marginLeft: "auto" }}>
          <a
            href="/api/admin/llm-feedback-export"
            download="llm_negative_feedback.jsonl"
            title="미채택 케이스(ai_draft / operator_html / reason)를 JSONL 로 export. SFT/DPO 학습 데이터로 활용."
          >
            <button type="button">⬇ LLM 피드백 export (JSONL)</button>
          </a>
        </div>
      </div>

      <CreateForm kind={kind} onCreated={refresh} />

      {isLoading && <LoadingView hint="프롬프트 버전 목록을 불러오는 중…" />}
      {isError && <ErrorView error={error} title="프롬프트 조회 실패" onRetry={refresh} />}
      {data && (
        <div>
          <h2 style={{ marginBottom: 8 }}>
            {kind} 버전 목록 ({data.length}건)
          </h2>
          {data.length === 0 && (
            <EmptyView
              title={`아직 ${kind} 버전이 없습니다`}
              hint="위 폼에서 첫 버전을 작성하고 [+ 추가 + 활성화] 로 즉시 적용하세요."
            />
          )}
          {data.map((p) => (
            <PromptCard key={p.id} p={p} onChanged={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}

function CreateForm({ kind, onCreated }: { kind: PromptKind; onCreated: () => void }) {
  const [content, setContent] = useState("");
  const [note, setNote] = useState("");
  const [activate, setActivate] = useState(false);
  const [previewResult, setPreviewResult] = useState<{ ok: boolean; text: string } | null>(null);

  const create = useMutation({
    mutationFn: () => createPrompt({ kind, content, note: note || undefined, activate }),
    onSuccess: () => {
      setContent("");
      setNote("");
      setActivate(false);
      setPreviewResult(null);
      onCreated();
    },
  });
  const preview = useMutation({
    mutationFn: () => previewPrompt({ kind, content }),
    onSuccess: (r) => {
      if (r.ok) setPreviewResult({ ok: true, text: r.rendered ?? "" });
      else setPreviewResult({ ok: false, text: r.error ?? "(알 수 없는 오류)" });
    },
  });

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>새 버전 작성 ({kind})</h2>
      <p className="muted small">
        system 프롬프트 본문을 입력하세요. Jinja2 변수: <code>ticket.title</code>,{" "}
        <code>ticket.body</code>
        {kind === "DRAFT" && (
          <>
            , <code>chunks[i].source_title</code>, <code>chunks[i].text</code>
          </>
        )}
      </p>
      <textarea
        rows={10}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="당신은 SPIM/SBOM 운영팀의 VOC 분류 보조원입니다. ..."
        style={{
          width: "100%",
          padding: 10,
          border: "1px solid var(--border)",
          borderRadius: 6,
          fontFamily: "ui-monospace, Menlo, Consolas, monospace",
          fontSize: 12,
        }}
      />
      <div className="form-row" style={{ marginTop: 8 }}>
        <label style={{ flex: "1 1 60%" }}>
          <span>비고 (변경 사유)</span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="예: citation 강제 추가"
          />
        </label>
        <label
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: 6,
            flex: "0 0 auto",
          }}
        >
          <input
            type="checkbox"
            checked={activate}
            onChange={(e) => setActivate(e.target.checked)}
          />
          <span>생성 즉시 활성화</span>
        </label>
        <button
          type="button"
          disabled={!content.trim() || preview.isPending}
          onClick={() => preview.mutate()}
        >
          {preview.isPending ? "렌더 중…" : "샘플 렌더 미리보기"}
        </button>
        <button
          type="button"
          className="primary"
          disabled={!content.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "저장 중…" : activate ? "+ 추가 + 활성화" : "+ 추가"}
        </button>
      </div>
      {previewResult && (
        <div
          className={`banner ${previewResult.ok ? "ok" : "err"}`}
          style={{
            whiteSpace: "pre-wrap",
            fontFamily: "ui-monospace, Menlo, Consolas, monospace",
            fontSize: 12,
          }}
        >
          {previewResult.ok ? "── 샘플 렌더 결과 ──\n\n" : "── 렌더 오류 ──\n\n"}
          {previewResult.text}
        </div>
      )}
      {create.isError && (
        <div className="banner err">저장 실패: {(create.error as Error).message}</div>
      )}
    </div>
  );
}

function PromptCard({
  p,
  onChanged,
}: {
  p: PromptTemplateOut;
  onChanged: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const activate = useMutation({
    mutationFn: () => activatePrompt(p.id),
    onSuccess: onChanged,
  });
  return (
    <div className="card" style={{ borderColor: p.is_active ? "var(--success)" : undefined }}>
      <div className="panel-header" style={{ alignItems: "center" }}>
        <div>
          <strong style={{ fontSize: 15 }}>
            {p.kind} · v{p.version}
          </strong>
          {p.is_active && (
            <span className="status-pill ok" style={{ marginLeft: 8 }}>
              활성
            </span>
          )}
          {p.note && (
            <span className="muted small" style={{ marginLeft: 8 }}>
              · {p.note}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button type="button" onClick={() => setExpanded((v) => !v)}>
            {expanded ? "접기" : "내용 보기"}
          </button>
          {!p.is_active && (
            <button
              type="button"
              className="primary"
              disabled={activate.isPending}
              onClick={() => activate.mutate()}
            >
              {activate.isPending ? "활성화 중…" : "이 버전 활성화"}
            </button>
          )}
        </div>
      </div>
      <div className="muted small" style={{ marginTop: 4 }}>
        ID #{p.id} · 생성일{" "}
        {p.created_at ? new Date(p.created_at).toLocaleString("ko-KR") : "—"}
      </div>
      {expanded && (
        <pre
          style={{
            marginTop: 8,
            background: "var(--bg)",
            padding: 10,
            borderRadius: 6,
            fontSize: 12,
            whiteSpace: "pre-wrap",
            maxHeight: 360,
            overflow: "auto",
          }}
        >
          {p.content}
        </pre>
      )}
    </div>
  );
}
