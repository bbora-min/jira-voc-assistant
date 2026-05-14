import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getKpiSummary, getRejectionReasons } from "@/api/kpi";
import { ErrorView, LoadingView } from "@/components/feedback/StateView";

function fmtPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function fmtMs(v: number): string {
  if (v < 1000) return `${v.toFixed(0)}ms`;
  if (v < 60_000) return `${(v / 1000).toFixed(1)}s`;
  if (v < 3_600_000) return `${(v / 60_000).toFixed(1)}분`;
  return `${(v / 3_600_000).toFixed(2)}시간`;
}

export function KpiDashboardPage() {
  const summary = useQuery({
    queryKey: ["kpi-summary"],
    queryFn: () => getKpiSummary({ group_by: "day" }),
  });
  const reasons = useQuery({
    queryKey: ["kpi-rejection-reasons"],
    queryFn: () => getRejectionReasons({ limit: 20 }),
  });

  if (summary.isLoading) {
    return <LoadingView hint="KPI 집계 결과를 불러오는 중…" />;
  }
  if (summary.isError || !summary.data) {
    return (
      <ErrorView
        title="KPI 조회 실패"
        error={summary.error ?? "알 수 없는 오류"}
        onRetry={() => summary.refetch()}
      />
    );
  }

  const s = summary.data;

  return (
    <div>
      <div className="page-header">
        <h1>KPI 대시보드</h1>
        <span className="muted small">
          기간: {s.period.from} ~ {s.period.to} · group_by={s.period.group_by}
        </span>
      </div>

      <div className="kpi-cards">
        <KpiCardBox
          label="AI 채택률"
          value={fmtPct(s.cards.adoption_rate.value)}
          sub={`승인 ${s.cards.adoption_rate.num} / (승인+미채택) ${s.cards.adoption_rate.den}`}
          accent="#2c66ff"
        />
        <KpiCardBox
          label="분류 정확도"
          value={fmtPct(s.cards.classification_accuracy.value)}
          sub={`수정 ${s.cards.classification_accuracy.den! - s.cards.classification_accuracy.num!} / 생성 ${s.cards.classification_accuracy.den}`}
          accent="#2f9e44"
        />
        <KpiCardBox
          label="평균 수정 거리"
          value={s.cards.avg_edit_distance.value.toFixed(1)}
          sub={`표본 ${s.cards.avg_edit_distance.samples}건 (Levenshtein)`}
          accent="#d97706"
        />
        <KpiCardBox
          label="평균 응답 시간"
          value={fmtMs(s.cards.avg_response_ms.value)}
          sub={`표본 ${s.cards.avg_response_ms.samples}건 (티켓 접수~Jira 등록)`}
          accent="#9333ea"
        />
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>일별 추이 — 생성/승인/미채택 + 채택률</h2>
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer>
            <ComposedChart data={s.series} margin={{ top: 8, right: 20, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e4e6eb" />
              <XAxis dataKey="bucket" fontSize={11} />
              <YAxis yAxisId="left" fontSize={11} allowDecimals={false} />
              <YAxis yAxisId="right" orientation="right" fontSize={11} domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
              <Tooltip formatter={((v: unknown, name: unknown) => {
                if (name === "채택률" && typeof v === "number") return fmtPct(v);
                return v as never;
              }) as never} />
              <Legend />
              <Bar yAxisId="left" dataKey="generated" fill="#bdcaff" name="생성" stackId="a" />
              <Bar yAxisId="left" dataKey="approved" fill="#2c66ff" name="승인" stackId="b" />
              <Bar yAxisId="left" dataKey="rejected" fill="#d97706" name="미채택" stackId="b" />
              <Line yAxisId="right" type="monotone" dataKey="adoption_rate" stroke="#2f9e44" strokeWidth={2} name="채택률" dot />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="kpi-row">
        <div className="card" style={{ flex: 1 }}>
          <h2 style={{ marginTop: 0 }}>일별 평균 응답시간 / 수정거리</h2>
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <ComposedChart data={s.series} margin={{ top: 8, right: 20, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e4e6eb" />
                <XAxis dataKey="bucket" fontSize={11} />
                <YAxis yAxisId="left" fontSize={11} />
                <YAxis yAxisId="right" orientation="right" fontSize={11} />
                <Tooltip
                  formatter={((v: unknown, name: unknown) => {
                    if (name === "평균 응답시간" && typeof v === "number") return fmtMs(v);
                    if (name === "평균 수정거리" && typeof v === "number") return v.toFixed(1);
                    return v as never;
                  }) as never}
                />
                <Legend />
                <Line yAxisId="left" type="monotone" dataKey="avg_response_ms" stroke="#9333ea" name="평균 응답시간" />
                <Line yAxisId="right" type="monotone" dataKey="avg_edit_distance" stroke="#d97706" name="평균 수정거리" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card" style={{ flex: 1 }}>
          <h2 style={{ marginTop: 0 }}>미채택 사유 키워드 빈도</h2>
          {reasons.isLoading && <div className="muted">불러오는 중…</div>}
          {reasons.data && reasons.data.top_keywords.length === 0 && (
            <div className="muted">아직 미채택 사유가 없습니다.</div>
          )}
          {reasons.data && reasons.data.top_keywords.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {reasons.data.top_keywords.map((kw) => (
                <span
                  key={kw.keyword}
                  className="kw-chip"
                  style={{ fontSize: 10 + Math.min(8, kw.count * 2) }}
                >
                  {kw.keyword}
                  <span className="muted small" style={{ marginLeft: 4 }}>×{kw.count}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>최근 미채택 사유 ({reasons.data?.total ?? 0}건 중 최대 20건)</h2>
        {reasons.data && reasons.data.items.length === 0 && (
          <div className="muted">아직 미채택 사유가 없습니다.</div>
        )}
        {reasons.data && reasons.data.items.length > 0 && (
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: 100 }}>티켓</th>
                <th>제목</th>
                <th>미채택 사유 (LLM 학습용)</th>
                <th style={{ width: 80 }}>수정거리</th>
                <th style={{ width: 130 }}>일시</th>
              </tr>
            </thead>
            <tbody>
              {reasons.data.items.map((r) => (
                <tr key={`${r.ticket_id}-${r.created_at}`}>
                  <td className="mono small">{r.jira_key}</td>
                  <td>{r.ticket_title}</td>
                  <td style={{ whiteSpace: "pre-wrap" }}>{r.reason}</td>
                  <td className="mono small">{r.edit_distance ?? "—"}</td>
                  <td className="muted small">
                    {r.created_at ? new Date(r.created_at).toLocaleString("ko-KR") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function KpiCardBox({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub: string;
  accent: string;
}) {
  return (
    <div className="kpi-card" style={{ borderTop: `3px solid ${accent}` }}>
      <div className="kpi-card-label">{label}</div>
      <div className="kpi-card-value" style={{ color: accent }}>
        {value}
      </div>
      <div className="kpi-card-sub muted small">{sub}</div>
    </div>
  );
}
