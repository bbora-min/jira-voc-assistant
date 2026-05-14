import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getWS } from "@/lib/ws";

interface TicketEvent {
  type: string;
  id?: string;
  payload?: { id: number; jira_key: string; title?: string; status?: string };
}

/** WebSocket으로 들어오는 ticket_created/ticket_updated 이벤트를
 *  TanStack Query 캐시에 반영해 목록을 자동 새로고침한다. */
export function useTicketEvents() {
  const qc = useQueryClient();
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    const ws = getWS();
    return ws.subscribe((raw) => {
      const evt = raw as TicketEvent;
      if (!evt || typeof evt !== "object") return;
      if (evt.type === "ticket_created" || evt.type === "ticket_updated") {
        qc.invalidateQueries({ queryKey: ["tickets"] });
        if (evt.payload?.id) {
          qc.invalidateQueries({ queryKey: ["ticket", evt.payload.id] });
        }
      }
    });
  }, [qc]);
}
