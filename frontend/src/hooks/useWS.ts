import { useEffect, useRef, useState } from "react";
import { getWS } from "@/lib/ws";

export function useWSStatus() {
  const [status, setStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [lastMessage, setLastMessage] = useState<unknown>(null);
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    const ws = getWS();

    const unsubscribe = ws.subscribe((msg) => {
      setLastMessage(msg);
      setStatus("open");
    });
    return unsubscribe;
  }, []);

  return { status, lastMessage };
}
