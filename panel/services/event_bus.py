"""In-memory async broadcast hub for WebSocket event clients."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

CHANNELS = frozenset(
    {
        "status",
        "telemetry",
        "pull_progress",
        "steamcmd_progress",
        "compile_progress",
        "audit_log",
        "console_tail",
    }
)


@dataclass
class _Client:
    ws: WebSocket
    channels: set[str] = field(default_factory=lambda: set(CHANNELS))


class EventBus:
    def __init__(self) -> None:
        self._clients: dict[int, _Client] = {}
        self._lock = asyncio.Lock()
        self._next_id = 0
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket, channels: set[str] | None = None) -> int:
        async with self._lock:
            client_id = self._next_id
            self._next_id += 1
            allowed = set(channels or CHANNELS) & CHANNELS
            self._clients[client_id] = _Client(ws=ws, channels=allowed or set(CHANNELS))
            return client_id

    async def disconnect(self, client_id: int) -> None:
        async with self._lock:
            self._clients.pop(client_id, None)

    async def has_subscribers(self, channel: str) -> bool:
        async with self._lock:
            return any(channel in client.channels for client in self._clients.values())

    async def publish(self, channel: str, data: Any) -> None:
        if channel not in CHANNELS:
            return
        envelope = {"channel": channel, "data": data, "ts": time.time()}
        async with self._lock:
            targets = [
                (client_id, client)
                for client_id, client in list(self._clients.items())
                if channel in client.channels
            ]
        dead: list[int] = []
        for client_id, client in targets:
            try:
                await client.ws.send_json(envelope)
            except Exception:
                dead.append(client_id)
        if dead:
            async with self._lock:
                for client_id in dead:
                    self._clients.pop(client_id, None)

    def publish_threadsafe(self, channel: str, data: Any) -> None:
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
        loop.call_soon_threadsafe(lambda: asyncio.create_task(self.publish(channel, data)))


bus = EventBus()


def emit(channel: str, data: Any) -> None:
    """Fire-and-forget emit from sync or async code."""
    bus.publish_threadsafe(channel, data)
