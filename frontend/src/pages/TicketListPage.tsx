import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { listTickets, injectRandom } from "@/api/tickets";
import { StatusTabs } from "@/components/tickets/StatusTabs";
import { TicketRow } from "@/components/tickets/TicketRow";
import { EmptyView, ErrorView, LoadingView } from "@/components/feedback/StateView";
import { useTicketEvents } from "@/hooks/useTicketEvents";
import type { TicketStatus } from "@/types/api";

export function TicketListPage() {
  useTicketEvents();
  const [params, setParams] = useSearchParams();
  const initial = (params.get("status") as TicketStatus | null) ?? "PENDING";
  const [active, setActive] = useState<TicketStatus | "ALL">(initial);
  const [busy, setBusy] = useState(false);
  const [lastInject, setLastInject] = useState<string | null>(null);

  const onChange = (s: TicketStatus | "ALL") => {
    setActive(s);
    if (s === "ALL") params.delete("status");
    else params.set("status", s);
    setParams(params, { replace: true });
  };

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["tickets", active],
    queryFn: () =>
      listTickets({
        status: active === "ALL" ? undefined : active,
        limit: 50,
      }),
    refetchOnMount: "always",
  });

  const handleInject = async () => {
    setBusy(true);
    try {
      const r = await injectRandom();
      setLastInject(`샘플 주입: ${r.jira_key} (${r.sample})`);
    } catch (e) {
      setLastInject(`주입 실패: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>티켓 목록</h1>
        <div className="page-actions">
          <button type="button" onClick={() => refetch()}>새로고침</button>
          <button type="button" className="primary" onClick={handleInject} disabled={busy}>
            {busy ? "주입 중…" : "샘플 webhook 주입"}
          </button>
        </div>
      </div>

      {lastInject && <div className="inject-banner">{lastInject}</div>}

      <StatusTabs
        active={active}
        counts={data?.counts}
        total={data?.total}
        onChange={onChange}
      />

      {isLoading && <LoadingView hint="티켓 목록을 불러오는 중…" />}
      {isError && (
        <ErrorView error={error} onRetry={() => refetch()} title="티켓 조회 실패" />
      )}
      {data && data.items.length === 0 && (
        <EmptyView
          title="해당 상태의 티켓이 없습니다"
          hint="다른 탭을 선택하거나 '샘플 webhook 주입' 으로 시드를 만들어 보세요."
        />
      )}

      {data && data.items.length > 0 && (
        <div className="ticket-list">
          <div className="ticket-row ticket-row-head">
            <div>Jira Key</div>
            <div>제목</div>
            <div>상태</div>
            <div>접수 시각</div>
          </div>
          {data.items.map((t) => (
            <TicketRow key={t.id} t={t} />
          ))}
        </div>
      )}
    </div>
  );
}
