"""WebSocket endpoint. Phase 1: connection lifecycle + ping echo."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, WebSocket, WebSocketDisconnect

from app.core.ws_manager import get_ws_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/tickets")
async def ws_tickets(
    websocket: WebSocket,
    x_forwarded_user: str | None = Header(default=None),
) -> None:
    user_id = x_forwarded_user or "_anon"
    manager = get_ws_manager()
    # Phase 7.5: ?last_event_id=N 으로 누락된 메시지 replay 요청 가능
    last_event_id_raw = websocket.query_params.get("last_event_id")
    last_event_id: int | None = None
    if last_event_id_raw and last_event_id_raw.isdigit():
        last_event_id = int(last_event_id_raw)
    await manager.connect(websocket, user_id=user_id, last_event_id=last_event_id)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "reason": "invalid_json"}))
                continue
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "ts": msg.get("ts")}))
            else:
                await websocket.send_text(
                    json.dumps({"type": "ack", "received": msg.get("type", "unknown")})
                )
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, user_id=user_id)
