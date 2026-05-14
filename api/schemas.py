from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MemorySet(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    value: Any


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    source: str = "chat"
    confirmed: bool = False
    speak: bool = False


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=1000)
    confirmed: bool = False


class ToolRequest(BaseModel):
    tool: Literal["read_file", "write_file", "run_command", "launch_app", "execute_python", "monitor_processes"]
    args: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=2000)
    run_at: str | float | int | None = None
    delay_seconds: int | None = Field(default=None, ge=0, le=31_536_000)
    interval_seconds: int | None = Field(default=None, ge=10, le=31_536_000)
    priority: int = Field(default=5, ge=1, le=10)


class VoiceTranscript(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)
    speak: bool = True


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class SystemAction(BaseModel):
    action: Literal["open_url", "open_path", "speak", "noop"]
    value: str | None = None
