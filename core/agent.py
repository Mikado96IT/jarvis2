from __future__ import annotations

import queue
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus

from core.llm import OllamaClient
from memory import MemoryStore
from tools import ToolEngine


SYSTEM_PROMPT = """Sei JARVIS, assistente operativo locale. Rispondi in modo breve e operativo.
Non inventare strumenti. Se serve agire sul PC, usa solo i tool disponibili nel sistema locale.
Mantieni un tono professionale e diretto."""


@dataclass
class AgentState:
    status: str = "ONLINE"
    last_input: str | None = None
    last_output: str | None = None
    active_task: str | None = None
    queue_size: int = 0
    updated_at: float = field(default_factory=time.time)


class JarvisAgent:
    def __init__(self, store: MemoryStore, tools: ToolEngine, llm: OllamaClient):
        self.store = store
        self.tools = tools
        self.llm = llm
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.state = AgentState()

    def _set_status(self, status: str, active_task: str | None = None) -> None:
        self.state.status = status
        self.state.active_task = active_task
        self.state.queue_size = self.queue.qsize()
        self.state.updated_at = time.time()

    def snapshot(self) -> dict[str, Any]:
        self.state.queue_size = self.queue.qsize()
        return self.state.__dict__.copy()

    def enqueue(self, text: str, source: str = "queue", confirmed: bool = False) -> dict[str, Any]:
        item = {"text": text, "source": source, "confirmed": confirmed, "created_at": time.time()}
        self.queue.put(item)
        self._set_status("QUEUED")
        self.store.log_event("info", "Input accodato", {"source": source, "text": text[:160]})
        return {"ok": True, "queue_size": self.queue.qsize()}

    def process_queue_once(self) -> dict[str, Any] | None:
        try:
            item = self.queue.get_nowait()
        except queue.Empty:
            self._set_status("ONLINE")
            return None
        return self.handle_input(item["text"], source=item["source"], confirmed=item.get("confirmed", False))

    def _recent_messages(self, user_text: str) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        memory = self.store.get_memory()
        if memory:
            messages.append({"role": "system", "content": f"Memoria persistente: {memory}"[:1800]})
        for row in self.store.recent_conversation(limit=8):
            if row["role"] in {"user", "assistant"}:
                messages.append({"role": row["role"], "content": row["content"]})
        messages.append({"role": "user", "content": user_text})
        return messages

    def _fallback_answer(self, text: str) -> str:
        lower = text.lower()
        if "ollama" in lower:
            return "Ollama non risulta attivo su 127.0.0.1:11434. Il sistema resta operativo con fallback locale; installando Ollama userò automaticamente il modello configurato."
        if "cosa puoi fare" in lower or "help" in lower or "aiuto" in lower:
            return "Posso eseguire comandi consentiti, leggere/scrivere file, aprire app o URL, creare task schedulati, monitorare il sistema e ricordare informazioni."
        if "stato" in lower or "sistema" in lower:
            snap = self.tools.system_snapshot()
            return f"Sistema online. CPU {snap['cpu_percent']:.0f}%, RAM {snap['ram_percent']:.0f}%, disco {snap['disk_percent']:.0f}%."
        return "Operativo. Dimmi un comando, una domanda o un task da schedulare."

    def _parse_intent(self, text: str) -> dict[str, Any] | None:
        raw = text.strip()
        lower = raw.lower()
        if lower.startswith("/cmd "):
            return {"tool": "run_command", "args": {"command": raw[5:].strip()}}
        if lower.startswith("esegui comando "):
            return {"tool": "run_command", "args": {"command": raw[15:].strip()}}
        if lower.startswith("run:"):
            return {"tool": "run_command", "args": {"command": raw[4:].strip()}}
        if lower.startswith("/read "):
            return {"tool": "read_file", "args": {"path": raw[6:].strip()}}
        if lower.startswith("/open "):
            return {"tool": "launch_app", "args": {"name": raw[6:].strip()}}
        if lower.startswith("apri "):
            return {"tool": "launch_app", "args": {"name": raw[5:].strip()}}
        if lower.startswith("/py "):
            return {"tool": "execute_python", "args": {"code": raw[4:].strip()}}
        if lower in {"stato sistema", "sistema", "status", "/status"}:
            return {"tool": "system_snapshot", "args": {}}
        if lower in {"processi", "/processes", "monitor processi"}:
            return {"tool": "monitor_processes", "args": {}}
        if self._looks_like_music_request(lower):
            return {"tool": "play_music", "args": {"query": self._music_query(raw)}}
        alarm = self._parse_alarm(raw)
        if alarm:
            return {"tool": "schedule_alarm", "args": alarm}
        match = re.match(r"^(ricorda|memorizza)\s+([^=:\s]+)\s*[=:]\s*(.+)$", raw, re.IGNORECASE)
        if match:
            return {"tool": "memory_set", "args": {"key": match.group(2), "value": match.group(3)}}
        match = re.match(r"^schedula\s+(\d+)\s+secondi\s*:\s*(.+)$", raw, re.IGNORECASE)
        if match:
            return {"tool": "schedule_delay", "args": {"delay": int(match.group(1)), "action": match.group(2)}}
        return None

    def _looks_like_music_request(self, lower: str) -> bool:
        verbs = ("metti", "avvia", "riproduci", "suona", "fammi sentire", "ascolta")
        nouns = ("canzone", "musica", "playlist", "brano")
        return any(verb in lower for verb in verbs) and any(noun in lower for noun in nouns)

    def _music_query(self, text: str) -> str:
        cleaned = re.sub(r"\b(jarvis|metti|avvia|riproduci|suona|fammi sentire|ascolta|una|un|la|il)\b", " ", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.:;")
        return cleaned or "musica"

    def _parse_alarm(self, text: str) -> dict[str, Any] | None:
        lower = text.lower()
        if not any(word in lower for word in ("sveglia", "timer", "promemoria", "ricordami")):
            return None

        now = datetime.now()
        message = "Sveglia"
        message_match = re.search(r"(?:per|di|che)\s+(.+)$", text, re.IGNORECASE)
        if message_match:
            message = message_match.group(1).strip(" .,:;") or message

        relative = re.search(r"\b(?:tra|fra)\s+(\d+|un|una)\s+(secondi|secondo|minuti|minuto|ore|ora)\b", lower)
        if relative:
            amount_text, unit = relative.groups()
            amount = 1 if amount_text in {"un", "una"} else int(amount_text)
            if unit.startswith("second"):
                run_at = now + timedelta(seconds=amount)
            elif unit.startswith("minut"):
                run_at = now + timedelta(minutes=amount)
            else:
                run_at = now + timedelta(hours=amount)
            return {"run_at": run_at.timestamp(), "message": message, "label": run_at.strftime("%H:%M")}

        clock = re.search(r"\b(?:alle|per le|a)\s+(\d{1,2})(?:[:.](\d{2}))?\b", lower)
        if clock:
            hour = int(clock.group(1))
            minute = int(clock.group(2) or 0)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                run_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if "domani" in lower or run_at <= now:
                    run_at += timedelta(days=1)
                return {"run_at": run_at.timestamp(), "message": message, "label": run_at.strftime("%H:%M")}
        return None

    def handle_input(self, text: str, source: str = "chat", confirmed: bool = False) -> dict[str, Any]:
        self._set_status("PROCESSING", text[:100])
        self.state.last_input = text
        self.store.add_conversation("user", text, source=source)

        intent = self._parse_intent(text)
        result: dict[str, Any]
        if intent:
            self._set_status("EXECUTING", intent["tool"])
            result = self._execute_intent(intent, confirmed=confirmed)
            response = self._summarize_tool_result(intent["tool"], result)
        else:
            llm_result = self.llm.chat(self._recent_messages(text))
            if llm_result.get("ok"):
                response = llm_result["content"].strip() or self._fallback_answer(text)
                result = {"ok": True, "brain": llm_result}
            else:
                response = self._fallback_answer(text)
                result = {"ok": True, "brain": llm_result, "fallback": True}

        self.store.add_conversation("assistant", response, source=source)
        self.store.log_event("info", "Interazione agente completata", {"source": source, "ok": result.get("ok", False)})
        self.state.last_output = response
        self._set_status("ONLINE")
        return {"ok": result.get("ok", False), "response": response, "result": result, "agent": self.snapshot()}

    def _execute_intent(self, intent: dict[str, Any], confirmed: bool = False) -> dict[str, Any]:
        tool = intent["tool"]
        args = intent.get("args", {})
        if tool == "system_snapshot":
            return {"ok": True, "snapshot": self.tools.system_snapshot()}
        if tool == "memory_set":
            self.store.set_memory(args["key"], args["value"])
            return {"ok": True, "key": args["key"], "value": args["value"]}
        if tool == "play_music":
            query = args["query"]
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            result = self.tools.launch_app(url, confirmed=True)
            result["query"] = query
            return result
        if tool == "schedule_alarm":
            task = self.store.create_task(
                title=f"Sveglia {args['label']}",
                action=f"alarm:{args['message']}",
                next_run=float(args["run_at"]),
                priority=1,
                source="agent",
            )
            return {"ok": True, "task": task, "label": args["label"], "message": args["message"]}
        if tool == "schedule_delay":
            task = self.store.create_task(
                title=f"Task agentico: {args['action'][:40]}",
                action=args["action"],
                next_run=time.time() + int(args["delay"]),
                source="agent",
            )
            return {"ok": True, "task": task}
        return self.tools.execute_tool(tool, args, confirmed=confirmed)

    def _summarize_tool_result(self, tool: str, result: dict[str, Any]) -> str:
        if result.get("needs_confirmation"):
            return f"Conferma richiesta: {result.get('error', 'azione sensibile')}."
        if not result.get("ok"):
            return f"Operazione fallita: {result.get('error', 'errore sconosciuto')}."
        if tool == "run_command":
            output = (result.get("stdout") or result.get("stderr") or "").strip()
            return output[:1200] if output else f"Comando completato con codice {result.get('returncode')}."
        if tool == "read_file":
            return str(result.get("content", ""))[:1600]
        if tool == "monitor_processes":
            processes = result.get("processes", [])[:5]
            return "Processi principali: " + ", ".join(f"{p['name']}({p['pid']})" for p in processes)
        if tool == "system_snapshot":
            snap = result["snapshot"]
            return f"CPU {snap['cpu_percent']:.0f}%, RAM {snap['ram_percent']:.0f}%, disco {snap['disk_percent']:.0f}%, processi {snap['process_count']}."
        if tool == "memory_set":
            return f"Memoria aggiornata: {result['key']}."
        if tool == "play_music":
            return f"Avvio musica: {result.get('query', 'richiesta')}."
        if tool == "schedule_alarm":
            return f"Sveglia impostata per le {result['label']}."
        if tool == "schedule_delay":
            return "Task schedulato e inserito nel loop autonomo."
        if tool == "launch_app":
            return f"Aperto: {result.get('target')}."
        return "Operazione completata."

    def execute_task_action(self, task: dict[str, Any]) -> dict[str, Any]:
        action = task["action"].strip()
        try:
            if action.startswith("command:"):
                return self.tools.run_command(action.removeprefix("command:").strip(), confirmed=True)
            if action.startswith("python:"):
                return self.tools.execute_python(action.removeprefix("python:").strip(), confirmed=True)
            if action.startswith("url:"):
                return self.tools.launch_app(action.removeprefix("url:").strip(), confirmed=True)
            if action.startswith("app:"):
                return self.tools.launch_app(action.removeprefix("app:").strip(), confirmed=True)
            if action.startswith("memory:"):
                payload = action.removeprefix("memory:").strip()
                key, sep, value = payload.partition("=")
                if not sep:
                    return {"ok": False, "error": "Formato memory richiesto: memory:chiave=valore"}
                self.store.set_memory(key.strip(), value.strip())
                return {"ok": True, "key": key.strip(), "value": value.strip()}
            if action.startswith("alarm:"):
                message = action.removeprefix("alarm:").strip() or "Sveglia"
                self.store.log_event("alarm", f"Sveglia: {message}", {"message": message})
                return {"ok": True, "alarm": True, "message": message, "speak": f"Sveglia. {message}"}
            if action.startswith("agent:"):
                return self.handle_input(action.removeprefix("agent:").strip(), source="scheduled", confirmed=True)
            return self.handle_input(action, source="scheduled", confirmed=True)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
