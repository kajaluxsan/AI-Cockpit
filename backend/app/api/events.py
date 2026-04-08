"""Live events WebSocket.

The cockpit frontend opens a single WebSocket to ``/api/events/ws`` and
receives JSON messages whenever something interesting happens (new inbound
message, chat reply, etc.). The frontend uses these to invalidate React
Query caches so the lists refresh without manual reload.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.services.event_broker import EventBroker, broker

router = APIRouter()


@router.websocket("/ws")
async def events_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await broker.subscribe()
    logger.debug("events.ws: client subscribed")
    try:
        # Send a hello so the client knows the stream is live
        await websocket.send_text('{"kind":"hello","payload":{}}')
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Keep-alive ping so proxies don't drop idle connections
                try:
                    await websocket.send_text('{"kind":"ping","payload":{}}')
                except Exception:
                    break
                continue
            await websocket.send_text(EventBroker.serialize(event))
    except WebSocketDisconnect:
        logger.debug("events.ws: client disconnected")
    except Exception as exc:
        logger.exception(f"events.ws: unhandled error: {exc}")
    finally:
        await broker.unsubscribe(queue)
        try:
            await websocket.close()
        except Exception:
            pass
