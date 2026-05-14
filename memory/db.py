from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any


def now_ts() -> float:
    return time.time()


def iso_from_ts(value: float | None) -> str | None:
    if value is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))


class MemoryStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "jarvis.sqlite3"
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self._migrate_legacy_json()

    def _init_schema(self) -> None:
        with self.lock, self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload TEXT,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    action TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 5,
                    status TEXT NOT NULL,
                    next_run REAL,
                    interval_seconds INTEGER,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_run REAL,
                    last_error TEXT
                );

                CREATE TABLE IF NOT EXISTS task_history (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    title TEXT NOT NULL,
                    action TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    result TEXT,
                    created_at REAL NOT NULL
                );
                """
            )

    def _migrate_legacy_json(self) -> None:
        memory_path = self.data_dir / "memory.json"
        logs_path = self.data_dir / "logs.json"
        if memory_path.exists() and not self.get_memory():
            try:
                data = json.loads(memory_path.read_text(encoding="utf-8"))
                for key, value in data.items():
                    self.set_memory(key, value)
            except (OSError, json.JSONDecodeError):
                pass
        if logs_path.exists() and not self.list_events(limit=1):
            try:
                logs = json.loads(logs_path.read_text(encoding="utf-8"))
                for entry in reversed(logs[-100:]):
                    self.log_event(entry.get("level", "info"), entry.get("message", ""), entry.get("payload"))
            except (OSError, json.JSONDecodeError):
                pass

    def _row_to_task(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["created_at_iso"] = iso_from_ts(item.get("created_at"))
        item["next_run_iso"] = iso_from_ts(item.get("next_run"))
        item["last_run_iso"] = iso_from_ts(item.get("last_run"))
        return item

    def set_memory(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO memory(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, payload, now_ts()),
            )

    def get_memory(self, key: str | None = None) -> dict[str, Any] | Any | None:
        with self.lock:
            if key is not None:
                row = self.conn.execute("SELECT value FROM memory WHERE key = ?", (key,)).fetchone()
                return None if row is None else json.loads(row["value"])
            rows = self.conn.execute("SELECT key, value FROM memory ORDER BY key").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def delete_memory(self, key: str) -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute("DELETE FROM memory WHERE key = ?", (key,))
            return cur.rowcount > 0

    def add_conversation(self, role: str, content: str, source: str = "chat") -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO conversations(id, role, content, source, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), role, content, source, now_ts()),
            )

    def recent_conversation(self, limit: int = 12) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT role, content, source, created_at FROM conversations ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def log_event(self, level: str, message: str, payload: Any | None = None) -> dict[str, Any]:
        event = {
            "id": str(uuid.uuid4()),
            "level": level,
            "message": message,
            "payload": payload,
            "created_at": now_ts(),
        }
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO events(id, level, message, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (event["id"], level, message, json.dumps(payload, ensure_ascii=False) if payload is not None else None, event["created_at"]),
            )
            self.conn.execute(
                "DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY created_at DESC LIMIT 500)"
            )
        return self._event_view(event)

    def _event_view(self, row: dict[str, Any] | sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        payload = data.get("payload")
        if isinstance(payload, str):
            try:
                data["payload"] = json.loads(payload)
            except json.JSONDecodeError:
                data["payload"] = payload
        data["created_at_iso"] = iso_from_ts(data.get("created_at"))
        return data

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, level, message, payload, created_at FROM events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._event_view(row) for row in rows]

    def create_task(
        self,
        title: str,
        action: str,
        next_run: float | None,
        interval_seconds: int | None = None,
        priority: int = 5,
        source: str = "user",
    ) -> dict[str, Any]:
        task_id = str(uuid.uuid4())
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO tasks(id, title, action, priority, status, next_run, interval_seconds, source, created_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (task_id, title, action, priority, next_run, interval_seconds, source, now_ts()),
            )
        self.log_event("info", f"Task creato: {title}", {"action": action})
        return self.get_task(task_id) or {}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return None if row is None else self._row_to_task(row)

    def list_tasks(self, include_done: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM tasks"
        params: tuple[Any, ...] = ()
        if not include_done:
            sql += " WHERE status != 'done'"
        sql += " ORDER BY status = 'active' DESC, priority ASC, COALESCE(next_run, 0) ASC, created_at DESC"
        with self.lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_task(row) for row in rows]

    def due_tasks(self, limit: int = 5) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'active' AND next_run IS NOT NULL AND next_run <= ?
                ORDER BY priority ASC, next_run ASC
                LIMIT ?
                """,
                (now_ts(), limit),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def update_task_status(self, task_id: str, status: str) -> dict[str, Any] | None:
        with self.lock, self.conn:
            self.conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        return self.get_task(task_id)

    def complete_task(self, task_id: str, ok: bool, result: Any = None, error: str | None = None) -> None:
        task = self.get_task(task_id)
        if not task:
            return
        next_run = None
        status = "done"
        if task.get("interval_seconds") and task.get("status") == "active":
            next_run = now_ts() + int(task["interval_seconds"])
            status = "active"
        with self.lock, self.conn:
            self.conn.execute(
                """
                UPDATE tasks
                SET status = ?, next_run = ?, last_run = ?, last_error = ?
                WHERE id = ?
                """,
                (status, next_run, now_ts(), error, task_id),
            )
            self.conn.execute(
                """
                INSERT INTO task_history(id, task_id, title, action, ok, result, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    task_id,
                    task["title"],
                    task["action"],
                    1 if ok else 0,
                    json.dumps(result, ensure_ascii=False, default=str),
                    now_ts(),
                ),
            )

    def delete_task(self, task_id: str) -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return cur.rowcount > 0

    def task_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM task_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["created_at_iso"] = iso_from_ts(item.get("created_at"))
            try:
                item["result"] = json.loads(item["result"])
            except (TypeError, json.JSONDecodeError):
                pass
            items.append(item)
        return items
