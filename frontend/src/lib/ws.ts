type Listener = (event: unknown) => void;

interface Options {
  url: string;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (e: Event) => void;
}

/** Reconnecting WebSocket with exponential backoff + simple event bus.
 *  Opens /ws/tickets, sends ping every 25s, exposes subscribe(listener) so React
 *  hooks can react to inbound events.
 *
 *  Phase 7.5: 마지막으로 받은 server-assigned seq 를 추적하고, 재연결 시
 *  ?last_event_id=N 쿼리 파라미터로 서버에 누락 메시지 replay 를 요청한다.
 */
export class ReconnectingWS {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private retryDelay = 1000;
  private readonly maxDelay = 30_000;
  private heartbeat: number | null = null;
  private closed = false;
  private lastEventId: string | null = null;
  private lastSeq: number = 0;   // server-assigned monotonic sequence

  constructor(private opts: Options) {
    this.connect();
  }

  private buildUrl(): string {
    if (this.lastSeq <= 0) return this.opts.url;
    const sep = this.opts.url.includes("?") ? "&" : "?";
    return `${this.opts.url}${sep}last_event_id=${this.lastSeq}`;
  }

  private connect() {
    if (this.closed) return;
    const ws = new WebSocket(this.buildUrl());
    this.ws = ws;
    ws.onopen = () => {
      this.retryDelay = 1000;
      this.startHeartbeat();
      this.opts.onOpen?.();
    };
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data?.id) this.lastEventId = data.id;
        if (typeof data?.seq === "number" && data.seq > this.lastSeq) {
          this.lastSeq = data.seq;
        }
        this.listeners.forEach((l) => l(data));
      } catch {
        this.listeners.forEach((l) => l(e.data));
      }
    };
    ws.onerror = (e) => this.opts.onError?.(e);
    ws.onclose = () => {
      this.stopHeartbeat();
      this.opts.onClose?.();
      if (!this.closed) {
        const jitter = Math.random() * 250;
        setTimeout(() => this.connect(), this.retryDelay + jitter);
        this.retryDelay = Math.min(this.retryDelay * 2, this.maxDelay);
      }
    };
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeat = window.setInterval(() => {
      this.send({ type: "ping", ts: Date.now() });
    }, 25_000);
  }

  private stopHeartbeat() {
    if (this.heartbeat) {
      window.clearInterval(this.heartbeat);
      this.heartbeat = null;
    }
  }

  send(msg: unknown) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  close() {
    this.closed = true;
    this.stopHeartbeat();
    this.ws?.close();
  }

  getLastEventId(): string | null {
    return this.lastEventId;
  }

  getLastSeq(): number {
    return this.lastSeq;
  }
}

let singleton: ReconnectingWS | null = null;

export function getWS(): ReconnectingWS {
  if (!singleton) {
    const wsBase = import.meta.env.VITE_WS_BASE || "";
    const url = wsBase ? `${wsBase}/ws/tickets` : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/tickets`;
    singleton = new ReconnectingWS({ url });
  }
  return singleton;
}
