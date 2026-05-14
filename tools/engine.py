from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path
from typing import Any

import psutil

from memory import MemoryStore


DANGEROUS_PATTERNS = [
    r"\brm\b",
    r"\bdel\b",
    r"\berase\b",
    r"\brmdir\b",
    r"\brd\b",
    r"\bRemove-Item\b",
    r"\bFormat-",
    r"\bshutdown\b",
    r"\bRestart-Computer\b",
    r"\bStop-Process\b",
    r"\btaskkill\b",
    r"\bgit\s+reset\b",
    r"\bgit\s+clean\b",
]


class ToolEngine:
    def __init__(self, root: Path, settings: dict[str, Any], store: MemoryStore):
        self.root = root.resolve()
        self.settings = settings
        self.store = store

    def _is_dangerous(self, command: str) -> bool:
        return any(re.search(pattern, command, re.IGNORECASE) for pattern in DANGEROUS_PATTERNS)

    def _command_allowed(self, command: str, confirmed: bool = False) -> tuple[bool, str | None]:
        normalized = command.strip().lower()
        if self._is_dangerous(command) and not confirmed:
            return False, "Azione distruttiva: conferma richiesta"
        allowed = self.settings.get("allowed_commands", [])
        if any(normalized == item.lower() or normalized.startswith(item.lower() + " ") for item in allowed):
            return True, None
        if confirmed or self.settings.get("allow_unlisted_commands", False):
            return True, None
        return False, "Comando fuori allowlist: conferma richiesta"

    def _resolve_path(self, path: str) -> Path:
        expanded = Path(os.path.expandvars(path)).expanduser()
        if not expanded.is_absolute():
            expanded = self.root / expanded
        return expanded.resolve()

    def read_file(self, path: str) -> dict[str, Any]:
        target = self._resolve_path(path)
        if not target.exists() or not target.is_file():
            return {"ok": False, "error": "File non trovato", "path": str(target)}
        content = target.read_text(encoding="utf-8", errors="replace")
        self.store.log_event("info", "File letto", {"path": str(target)})
        return {"ok": True, "path": str(target), "content": content}

    def write_file(self, path: str, content: str, confirmed: bool = False) -> dict[str, Any]:
        target = self._resolve_path(path)
        outside_workspace = not str(target).lower().startswith(str(self.root).lower())
        if outside_workspace and not confirmed:
            return {"ok": False, "needs_confirmation": True, "error": "Scrittura fuori workspace: conferma richiesta"}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.store.log_event("info", "File scritto", {"path": str(target), "bytes": len(content.encode("utf-8"))})
        return {"ok": True, "path": str(target), "bytes": len(content.encode("utf-8"))}

    def run_command(self, command: str, confirmed: bool = False, timeout: int | None = None) -> dict[str, Any]:
        allowed, reason = self._command_allowed(command, confirmed=confirmed)
        if not allowed:
            self.store.log_event("warning", "Comando bloccato", {"command": command, "reason": reason})
            return {"ok": False, "needs_confirmation": True, "error": reason, "command": command}

        if os.name == "nt":
            ps_command = (
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "$OutputEncoding = [System.Text.Encoding]::UTF8; "
                f"{command}"
            )
            shell = ["powershell", "-NoProfile", "-Command", ps_command]
        else:
            shell = ["/bin/sh", "-lc", command]

        started = time.time()
        try:
            completed = subprocess.run(
                shell,
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or int(self.settings.get("max_command_seconds", 20)),
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.store.log_event("error", "Comando scaduto", {"command": command})
            return {"ok": False, "error": "Timeout comando", "command": command}

        result = {
            "ok": completed.returncode == 0,
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-8000:],
            "elapsed_seconds": round(time.time() - started, 3),
        }
        self.store.log_event("info", "Comando eseguito", {"command": command, "returncode": completed.returncode})
        return result

    def launch_app(self, name: str, confirmed: bool = False) -> dict[str, Any]:
        value = name.strip()
        if not value:
            return {"ok": False, "error": "Nome app mancante"}
        try:
            if re.match(r"^https?://", value, re.IGNORECASE):
                webbrowser.open(value)
            elif os.name == "nt":
                os.startfile(value)  # type: ignore[attr-defined]
            else:
                subprocess.Popen([value], cwd=self.root)
        except Exception as exc:  # noqa: BLE001
            if not confirmed:
                cmd = f"Start-Process {json.dumps(value)}" if os.name == "nt" else value
                return self.run_command(cmd, confirmed=True)
            return {"ok": False, "error": str(exc), "target": value}
        self.store.log_event("info", "Applicazione/URL aperto", {"target": value})
        return {"ok": True, "target": value}

    def execute_python(self, code: str, confirmed: bool = False) -> dict[str, Any]:
        if self._is_dangerous(code) and not confirmed:
            return {"ok": False, "needs_confirmation": True, "error": "Codice potenzialmente distruttivo: conferma richiesta"}
        runtime_dir = self.root / "data" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", dir=runtime_dir, delete=False) as handle:
            handle.write(code)
            script = Path(handle.name)
        try:
            completed = subprocess.run(
                [sys.executable, str(script)],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(self.settings.get("max_command_seconds", 20)),
                check=False,
            )
            result = {
                "ok": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-8000:],
                "stderr": completed.stderr[-8000:],
            }
            self.store.log_event("info", "Script Python eseguito", {"returncode": completed.returncode})
            return result
        finally:
            try:
                script.unlink(missing_ok=True)
            except OSError:
                pass

    def monitor_processes(self, limit: int = 12) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = proc.info
                items.append(
                    {
                        "pid": info.get("pid"),
                        "name": info.get("name"),
                        "cpu_percent": info.get("cpu_percent") or 0,
                        "memory_percent": round(info.get("memory_percent") or 0, 2),
                        "status": info.get("status"),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        items.sort(key=lambda item: (item["cpu_percent"], item["memory_percent"]), reverse=True)
        return {"ok": True, "processes": items[:limit], "total": len(items)}

    def system_snapshot(self) -> dict[str, Any]:
        disk = psutil.disk_usage(str(self.root.drive + "\\") if os.name == "nt" and self.root.drive else str(self.root))
        battery = psutil.sensors_battery()
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.05),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": disk.percent,
            "battery_percent": None if battery is None else battery.percent,
            "power_plugged": None if battery is None else battery.power_plugged,
            "process_count": len(psutil.pids()),
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "workspace": str(self.root),
        }

    def execute_tool(self, name: str, args: dict[str, Any], confirmed: bool = False) -> dict[str, Any]:
        if name == "read_file":
            return self.read_file(str(args.get("path", "")))
        if name == "write_file":
            return self.write_file(str(args.get("path", "")), str(args.get("content", "")), confirmed=confirmed)
        if name == "run_command":
            return self.run_command(str(args.get("command", "")), confirmed=confirmed)
        if name == "launch_app":
            return self.launch_app(str(args.get("name", "")), confirmed=confirmed)
        if name == "execute_python":
            return self.execute_python(str(args.get("code", "")), confirmed=confirmed)
        if name == "monitor_processes":
            return self.monitor_processes()
        return {"ok": False, "error": f"Tool sconosciuto: {name}"}
