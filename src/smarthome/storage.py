from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


class EventStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._queue: Optional[asyncio.Queue] = None
        self._task: Optional[asyncio.Task] = None

    def _connect(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    ts REAL,
                    room TEXT,
                    device_id TEXT,
                    metric TEXT,
                    value TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS actuators (
                    ts REAL,
                    room TEXT,
                    device_id TEXT,
                    key TEXT,
                    value TEXT
                )
                """
            )
            self._conn.commit()

    async def start(self) -> None:
        self._connect()
        self._queue = asyncio.Queue()
        self._task = asyncio.create_task(self._writer())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None
        if self._conn:
            self._conn.commit()
            self._conn.close()
            self._conn = None
        self._queue = None

    async def _writer(self) -> None:
        assert self._conn is not None
        assert self._queue is not None
        cur = self._conn.cursor()
        while True:
            try:
                item = await self._queue.get()
                typ = item.get("type")
                if typ == "reading":
                    cur.execute(
                        "INSERT INTO readings (ts, room, device_id, metric, value) VALUES (?, ?, ?, ?, ?)",
                        (
                            float(item["ts"]),
                            str(item["room"]),
                            str(item["device_id"]),
                            str(item["metric"]),
                            json.dumps(item.get("value")),
                        ),
                    )
                elif typ == "actuator":
                    cur.execute(
                        "INSERT INTO actuators (ts, room, device_id, key, value) VALUES (?, ?, ?, ?, ?)",
                        (
                            float(item["ts"]),
                            str(item["room"]),
                            str(item["device_id"]),
                            str(item.get("metric") or "state"),
                            json.dumps(item.get("value")),
                        ),
                    )
                if self._queue.empty():
                    self._conn.commit()
            except asyncio.CancelledError:
                break

    async def enqueue(self, event: Dict[str, Any]) -> None:
        if not self._queue:
            return
        await self._queue.put(event)

    def query_readings(self, room: str, sensor_id: str, limit: int = 300) -> List[Tuple[float, Any]]:
        self._connect()
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT ts, value FROM readings WHERE room=? AND device_id=? ORDER BY ts DESC LIMIT ?",
            (room, sensor_id, limit),
        ).fetchall()
        rows.reverse()
        return [(float(ts), json.loads(val)) for ts, val in rows]

    def query_readings_since(self, room: str, sensor_id: str, since_ts: float) -> List[Tuple[float, Any]]:
        self._connect()
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT ts, value FROM readings WHERE room=? AND device_id=? AND ts>=? ORDER BY ts ASC",
            (room, sensor_id, since_ts),
        ).fetchall()
        return [(float(ts), json.loads(val)) for ts, val in rows]
