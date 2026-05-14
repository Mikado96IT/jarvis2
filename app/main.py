from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import ChatRequest, CommandRequest, MemorySet, SpeakRequest, SystemAction, TaskCreate, ToolRequest, VoiceTranscript
from core import JarvisAgent, OllamaClient
from memory import MemoryStore
from scheduler import BackgroundRuntime
from tools import ToolEngine
from voice import VoiceEngine, WakeWordDetector


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "settings.json"
WEB_DIR = ROOT / "web"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fallback, indent=2, ensure_ascii=False), encoding="utf-8")
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_suffix(path.suffix + ".broken")
        path.replace(backup)
        path.write_text(json.dumps(fallback, indent=2, ensure_ascii=False), encoding="utf-8")
        return fallback


def read_settings() -> dict[str, Any]:
    defaults = {
        "host": "127.0.0.1",
        "port": 8765,
        "assistant_name": "JARVIS",
        "wake_word": "jarvis",
        "data_dir": "data",
        "max_command_seconds": 20,
        "background_tick_seconds": 1,
        "system_monitor_seconds": 10,
        "allow_unlisted_commands": False,
        "ollama": {
            "host": "http://127.0.0.1:11434",
            "model": "llama3.2",
        },
        "voice": {
            "tts_enabled": True,
            "tts_rate": 175,
            "browser_stt_enabled": True,
            "push_to_talk": True,
        },
        "monitor_thresholds": {"cpu": 95, "ram": 95, "disk": 98},
        "allowed_commands": [
            "dir",
            "echo",
            "Get-ChildItem",
            "Get-Date",
            "Get-Process",
            "Get-Service",
            "ipconfig",
            "ping",
            "python --version",
            "py --version",
            "where",
            "whoami",
        ],
    }
    settings = load_json(CONFIG_PATH, defaults)
    merged = defaults | settings
    merged["ollama"] = defaults["ollama"] | settings.get("ollama", {})
    merged["voice"] = defaults["voice"] | settings.get("voice", {})
    merged["monitor_thresholds"] = defaults["monitor_thresholds"] | settings.get("monitor_thresholds", {})
    CONFIG_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return merged


settings = read_settings()
store = MemoryStore(ROOT / settings["data_dir"])
tools = ToolEngine(ROOT, settings, store)
llm = OllamaClient(settings["ollama"]["host"], settings["ollama"]["model"])
agent = JarvisAgent(store, tools, llm)
voice = VoiceEngine(settings, store)
runtime = BackgroundRuntime(store, agent, tools, settings, speaker=voice.speak)
wakeword = WakeWordDetector(settings["wake_word"])

app = FastAPI(title="JARVIS Iron Man Autonomous System", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:*", "http://localhost:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def parse_run_at(value: str | float | int | None, delay_seconds: int | None = None) -> float:
    if delay_seconds is not None:
        return time.time() + delay_seconds
    if value is None or value == "":
        return time.time()
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).strip()
    if cleaned.isdigit():
        return float(cleaned)
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00")).timestamp()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_at deve essere ISO-8601 o timestamp") from exc


@app.on_event("startup")
def startup() -> None:
    runtime.start()
    store.log_event("info", "JARVIS Iron Man System online", {"workspace": str(ROOT)})


@app.on_event("shutdown")
def shutdown() -> None:
    runtime.stop()
    store.log_event("info", "JARVIS arrestato")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/status")
def status() -> dict[str, Any]:
    memory = store.get_memory()
    ollama = llm.tags()
    return {
        "assistant": settings["assistant_name"],
        "wake_word": settings["wake_word"],
        "time": utc_now(),
        "system": tools.system_snapshot(),
        "agent": agent.snapshot(),
        "runtime": runtime.status(),
        "brain": {
            "provider": "ollama" if ollama.get("ok") else "local-fallback",
            "ollama_host": settings["ollama"]["host"],
            "model": settings["ollama"]["model"],
            "available": bool(ollama.get("ok")),
            "models": ollama.get("models", []),
        },
        "voice": settings["voice"],
        "tasks": store.list_tasks(include_done=False),
        "memory_count": len(memory),
        "events": store.list_events(limit=80),
    }


@app.get("/api/ollama/status")
def ollama_status() -> dict[str, Any]:
    data = llm.tags()
    return {
        "host": settings["ollama"]["host"],
        "model": settings["ollama"]["model"],
        "available": bool(data.get("ok")),
        **data,
    }


@app.post("/api/agent/chat")
def agent_chat(payload: ChatRequest) -> dict[str, Any]:
    result = agent.handle_input(payload.message, source=payload.source, confirmed=payload.confirmed)
    if payload.speak and result.get("response"):
        voice.speak(result["response"])
    return result


@app.post("/api/agent/queue")
def agent_queue(payload: ChatRequest) -> dict[str, Any]:
    return agent.enqueue(payload.message, source=payload.source, confirmed=payload.confirmed)


@app.get("/api/agent/status")
def agent_status() -> dict[str, Any]:
    return agent.snapshot()


@app.get("/api/memory")
def memory_all() -> dict[str, Any]:
    return store.get_memory()


@app.get("/api/memory/{key}")
def memory_get(key: str) -> dict[str, Any]:
    value = store.get_memory(key)
    if value is None:
        raise HTTPException(status_code=404, detail="Chiave non trovata")
    return {"key": key, "value": value}


@app.post("/api/memory")
def memory_set(payload: MemorySet) -> dict[str, Any]:
    store.set_memory(payload.key, payload.value)
    store.log_event("info", f"Memoria aggiornata: {payload.key}")
    return {"ok": True, "key": payload.key}


@app.delete("/api/memory/{key}")
def memory_delete(key: str) -> dict[str, Any]:
    deleted = store.delete_memory(key)
    if deleted:
        store.log_event("info", f"Memoria eliminata: {key}")
    return {"ok": True, "deleted": deleted}


@app.get("/api/tasks")
def tasks_all(include_done: bool = True) -> list[dict[str, Any]]:
    return store.list_tasks(include_done=include_done)


@app.post("/api/tasks")
def task_create(payload: TaskCreate) -> dict[str, Any]:
    return store.create_task(
        title=payload.title,
        action=payload.action,
        next_run=parse_run_at(payload.run_at, payload.delay_seconds),
        interval_seconds=payload.interval_seconds,
        priority=payload.priority,
        source="api",
    )


@app.patch("/api/tasks/{task_id}/toggle")
def task_toggle(task_id: str) -> dict[str, Any]:
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task non trovato")
    new_status = "paused" if task["status"] == "active" else "active"
    updated = store.update_task_status(task_id, new_status)
    return updated or {}


@app.delete("/api/tasks/{task_id}")
def task_delete(task_id: str) -> dict[str, Any]:
    return {"ok": True, "deleted": store.delete_task(task_id)}


@app.get("/api/tasks/history")
def task_history() -> list[dict[str, Any]]:
    return store.task_history(limit=80)


@app.post("/api/tools/execute")
def tool_execute(payload: ToolRequest) -> dict[str, Any]:
    return tools.execute_tool(payload.tool, payload.args, confirmed=payload.confirmed)


@app.post("/api/command")
def command(payload: CommandRequest) -> dict[str, Any]:
    return tools.run_command(payload.command, confirmed=payload.confirmed)


@app.post("/api/voice/transcript")
def voice_transcript(payload: VoiceTranscript) -> dict[str, Any]:
    detected = wakeword.detect(payload.transcript)
    if not detected["active"]:
        return {"ok": True, "wake": False, "detected": detected}
    command_text = str(detected["command"] or "stato sistema")
    result = agent.handle_input(command_text, source="voice", confirmed=False)
    if payload.speak and result.get("response"):
        voice.speak(result["response"])
    return {"ok": True, "wake": True, "detected": detected, "agent": result}


@app.post("/api/voice/speak")
def voice_speak(payload: SpeakRequest) -> dict[str, Any]:
    return voice.speak(payload.text)


@app.get("/api/events")
def events(limit: int = 100) -> list[dict[str, Any]]:
    return store.list_events(limit=limit)


@app.post("/api/system")
def system_action(payload: SystemAction) -> dict[str, Any]:
    if payload.action == "noop":
        return {"ok": True}
    if payload.action == "speak":
        return voice.speak(payload.value or "")
    if payload.action == "open_url":
        return tools.launch_app(payload.value or "", confirmed=True)
    if payload.action == "open_path":
        return tools.launch_app(payload.value or "", confirmed=True)
    raise HTTPException(status_code=400, detail="Azione non supportata")


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings["host"],
        port=int(settings["port"]),
        reload=False,
        log_level="info",
    )
