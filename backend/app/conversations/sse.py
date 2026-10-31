"""In-process SSE fan-out for chat threads and the owner inbox.

Single-process by design for v1. If the API is ever scaled to multiple instances, replace the
transport with Postgres ``LISTEN/NOTIFY`` — the event contract stays the same.
"""

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request

MERCHANT_CHANNEL = "merchant"
CONVERSATION_CHANNEL = "conversation"

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class EventHub:
    def __init__(self) -> None:
        self._subscribers: dict[tuple[str, object], set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, channel: str, key: object) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers[(channel, key)].add(queue)
        return queue

    def unsubscribe(self, channel: str, key: object, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get((channel, key))
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop((channel, key), None)

    def publish(self, channel: str, key: object, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get((channel, key), ())):
            if queue.full():
                try:
                    queue.get_nowait()  # drop the oldest event for slow clients
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)

    def subscriber_count(self, channel: str, key: object) -> int:
        return len(self._subscribers.get((channel, key), ()))


hub = EventHub()


def sse_frame(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


async def stream_events(
    request: Request,
    channel: str,
    key: object,
    *,
    keepalive_seconds: float = 15,
) -> AsyncIterator[str]:
    queue = hub.subscribe(channel, key)
    try:
        yield ": connected\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=keepalive_seconds)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield sse_frame(event)
    finally:
        hub.unsubscribe(channel, key, queue)
