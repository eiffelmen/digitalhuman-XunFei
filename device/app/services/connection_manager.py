"""
WebSocket 连接管理器，负责统一维护 key -> WebSocket 的映射。
"""
from __future__ import annotations

import asyncio
from enum import Enum
from typing import Dict, Optional

from fastapi import WebSocket, FastAPI


class ConnectionScope(str, Enum):
    APP = "app"
    WEB = "web"
    NEW_WEB = "new_web"


class ConnectionManager:
    """
    基于 asyncio.Lock 的轻量连接池管理。
    """

    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _make_key(scope: ConnectionScope, identifier: str) -> str:
        return f"{scope.value}:{identifier}"

    async def register(self, scope: ConnectionScope, identifier: str, websocket: WebSocket) -> str:
        key = self._make_key(scope, identifier)
        async with self._lock:
            self._connections[key] = websocket
        return key

    async def unregister(self, scope: ConnectionScope, identifier: str) -> None:
        key = self._make_key(scope, identifier)
        await self.unregister_by_key(key)

    async def unregister_by_key(self, key: str) -> None:
        async with self._lock:
            self._connections.pop(key, None)

    async def send(self, scope: ConnectionScope, identifier: str, message: str) -> bool:
        key = self._make_key(scope, identifier)
        return await self.send_by_key(key, message)

    async def send_by_key(self, key: str, message: str) -> bool:
        websocket = await self._get_connection(key)
        if not websocket:
            return False
        await websocket.send_text(message)
        return True

    async def _get_connection(self, key: str) -> Optional[WebSocket]:
        async with self._lock:
            return self._connections.get(key)

    async def list_keys(self) -> list[str]:
        async with self._lock:
            return list(self._connections.keys())

    async def count(self) -> int:
        async with self._lock:
            return len(self._connections)


def resolve_connection_manager(app: FastAPI) -> ConnectionManager:
    """
    尝试从 FastAPI app.state 中获取 ConnectionManager，不存在则懒加载一个。
    """
    manager: Optional[ConnectionManager] = getattr(app.state, "connection_manager", None)
    if manager is None:
        manager = ConnectionManager()
        app.state.connection_manager = manager
    return manager

