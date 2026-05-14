from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from core import JarvisAgent
from memory import MemoryStore
from tools import ToolEngine


class BackgroundRuntime:
    def __init__(
        self,
        store: MemoryStore,
        agent: JarvisAgent,
        tools: ToolEngine,
        settings: dict[str, Any],
        speaker: Callable[[str], dict[str, Any]] | None = None,
    ):
        self.store = store
        self.agent = agent
        self.tools = tools
        self.settings = settings
        self.speaker = speaker
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.started_at: float | None = None
        self.last_monitor_at = 0.0
        self.last_tick_at = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._loop, name="jarvis-background-runtime", daemon=True)
        self._thread.start()
        self.store.log_event("info", "Runtime autonomo avviato")

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "started_at": self.started_at,
            "last_tick_at": self.last_tick_at,
            "last_monitor_at": self.last_monitor_at,
        }

    def _loop(self) -> None:
        interval = float(self.settings.get("background_tick_seconds", 1))
        while not self._stop.is_set():
            self.last_tick_at = time.time()
            self._process_due_tasks()
            self.agent.process_queue_once()
            self._monitor_system()
            self._stop.wait(interval)

    def _process_due_tasks(self) -> None:
        for task in self.store.due_tasks(limit=5):
            self.store.log_event("info", f"Esecuzione task: {task['title']}", {"task_id": task["id"]})
            result = self.agent.execute_task_action(task)
            ok = bool(result.get("ok"))
            if ok and result.get("speak") and self.speaker:
                self.speaker(str(result["speak"]))
            self.store.complete_task(task["id"], ok=ok, result=result, error=None if ok else result.get("error"))

    def _monitor_system(self) -> None:
        monitor_seconds = int(self.settings.get("system_monitor_seconds", 10))
        if time.time() - self.last_monitor_at < monitor_seconds:
            return
        self.last_monitor_at = time.time()
        snapshot = self.tools.system_snapshot()
        thresholds = self.settings.get("monitor_thresholds", {"cpu": 95, "ram": 95, "disk": 98})
        if snapshot["cpu_percent"] >= thresholds.get("cpu", 95):
            self.store.log_event("warning", "CPU alta", snapshot)
        if snapshot["ram_percent"] >= thresholds.get("ram", 95):
            self.store.log_event("warning", "RAM alta", snapshot)
        if snapshot["disk_percent"] >= thresholds.get("disk", 98):
            self.store.log_event("warning", "Disco quasi pieno", snapshot)
