"""Diffusion temps reel des evenements d'un tournoi."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def join(self, tournament_id: int, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._rooms[tournament_id].add(ws)

    async def leave(self, tournament_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._rooms[tournament_id].discard(ws)

    async def broadcast(self, tournament_id: int, event: str, data: Any = None) -> None:
        async with self._lock:
            targets = list(self._rooms.get(tournament_id, ()))
        payload = {"event": event, "data": data}
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:  # pragma: no cover - client deconnecte
                await self.leave(tournament_id, ws)


hub = Hub()
