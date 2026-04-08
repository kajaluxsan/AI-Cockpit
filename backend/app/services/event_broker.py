"""In-process pub/sub broker for live UI events.

Very small and deliberately scoped: every WebSocket client maintains an
``asyncio.Queue`` in the broker's fanout set. Producers call
``publish(event)`` and the broker pushes the JSON blob to every queue.

This is in-memory and single-process — fine for one uvicorn worker. If the
backend ever scales to multiple workers, swap this module for a Redis
pub/sub without touching callers (the publish/subscribe API stays the same).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass
class Event:
    kind: str                 # e.g. "message.new", "chat.append"
    payload: dict[str, Any]


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, kind: str, payload: dict[str, Any]) -> None:
        event = Event(kind=kind, payload=payload)
        async with self._lock:
            queues = list(self._subscribers)
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Event broker queue full, dropping event for slow subscriber"
                )

    @staticmethod
    def serialize(event: Event) -> str:
        return json.dumps(
            {"kind": event.kind, "payload": event.payload}, ensure_ascii=False
        )


# Singleton used across the app
broker = EventBroker()


def publish_sync_safe(kind: str, payload: dict[str, Any]) -> None:
    """Publish from code that may or may not be inside a running loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.create_task(broker.publish(kind, payload))
    else:
        # No loop — we're in a sync context; run a small loop just for this
        asyncio.run(broker.publish(kind, payload))
