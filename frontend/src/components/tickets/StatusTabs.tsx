import type { TicketStatus } from "@/types/api";

const TABS: { key: TicketStatus | "ALL"; label: string }[] = [
  { key: "PENDING", label: "대기" },
  { key: "IN_PROGRESS", label: "처리 중" },
  { key: "DONE", label: "완료" },
  { key: "ALL", label: "전체" },
];

interface Props {
  active: TicketStatus | "ALL";
  counts?: Record<string, number>;
  total?: number;
  onChange: (s: TicketStatus | "ALL") => void;
}

export function StatusTabs({ active, counts, total, onChange }: Props) {
  return (
    <div className="status-tabs">
      {TABS.map((t) => {
        const n = t.key === "ALL" ? total : counts?.[t.key];
        const cls = t.key === active ? "tab active" : "tab";
        return (
          <button key={t.key} type="button" className={cls} onClick={() => onChange(t.key)}>
            {t.label}
            {typeof n === "number" && <span className="tab-count">{n}</span>}
          </button>
        );
      })}
    </div>
  );
}
