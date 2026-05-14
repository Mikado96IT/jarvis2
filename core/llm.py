from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class OllamaClient:
    def __init__(self, host: str = "http://127.0.0.1:11434", model: str = "llama3.2"):
        self.host = host.rstrip("/")
        self.model = model

    def _request(self, path: str, payload: dict[str, Any] | None = None, timeout: int = 20) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - local endpoint
            return json.loads(response.read().decode("utf-8"))

    def tags(self) -> dict[str, Any]:
        try:
            return {"ok": True, "models": self._request("/api/tags", timeout=3).get("models", [])}
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc), "models": []}

    def available(self) -> bool:
        return bool(self.tags().get("ok"))

    def chat(self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if tools:
            payload["tools"] = tools
        try:
            data = self._request("/api/chat", payload, timeout=60)
            content = data.get("message", {}).get("content", "")
            return {"ok": True, "provider": "ollama", "model": self.model, "content": content, "raw": data}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "provider": "fallback", "model": "local-rules", "error": str(exc)}
