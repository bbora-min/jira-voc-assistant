/** 공용 로딩/에러/엠프티 표시 컴포넌트 (Phase 7.6).
 *
 *  모든 페이지에서 동일한 톤으로 상태를 표시하기 위한 단순 wrapper.
 *  React Query 의 상태(isLoading / isError) 와 결합하기 좋게 design.
 */
import type { ReactNode } from "react";

interface CommonProps {
  hint?: string;
}

export function LoadingView({ hint = "불러오는 중…" }: CommonProps) {
  return (
    <div className="card state-view loading">
      <div className="spinner" aria-hidden />
      <div className="state-text">{hint}</div>
    </div>
  );
}

export function ErrorView({
  error,
  onRetry,
  title = "오류가 발생했습니다",
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const message = error instanceof Error ? error.message : String(error ?? "알 수 없는 오류");
  return (
    <div className="card err state-view">
      <strong>{title}</strong>
      <div className="state-text mono small" style={{ marginTop: 4 }}>{message}</div>
      {onRetry && (
        <div style={{ marginTop: 8 }}>
          <button type="button" onClick={onRetry}>다시 시도</button>
        </div>
      )}
    </div>
  );
}

export function EmptyView({
  title = "표시할 항목이 없습니다",
  hint,
  action,
}: {
  title?: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="card empty state-view">
      <div style={{ fontSize: 32, lineHeight: 1, opacity: 0.4, marginBottom: 8 }}>∅</div>
      <strong>{title}</strong>
      {hint && <div className="state-text small muted" style={{ marginTop: 4 }}>{hint}</div>}
      {action && <div style={{ marginTop: 12 }}>{action}</div>}
    </div>
  );
}
