from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, meeting_id: str) -> None:
        await websocket.accept()
        self.active_connections.setdefault(meeting_id, []).append(websocket)

    async def disconnect(self, websocket: WebSocket, meeting_id: str) -> None:
        connections = self.active_connections.get(meeting_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections and meeting_id in self.active_connections:
            del self.active_connections[meeting_id]

    async def broadcast(self, meeting_id: str, message: dict) -> None:
        connections = list(self.active_connections.get(meeting_id, []))
        stale: list[WebSocket] = []

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                stale.append(connection)

        for connection in stale:
            await self.disconnect(connection, meeting_id)


manager = ConnectionManager()
