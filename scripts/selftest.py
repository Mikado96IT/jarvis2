from __future__ import annotations

import json
import time
import urllib.request


BASE = "http://127.0.0.1:8765"


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=10) as response:  # noqa: S310 - local endpoint
        return json.loads(response.read().decode("utf-8"))


def post(path: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - local endpoint
        return json.loads(response.read().decode("utf-8"))


def delete(path: str):
    request = urllib.request.Request(BASE + path, method="DELETE")
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - local endpoint
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    status = get("/api/status")
    assert status["assistant"] == "JARVIS"
    assert status["runtime"]["running"] is True

    chat = post("/api/agent/chat", {"message": "stato sistema", "source": "selftest"})
    assert chat["ok"] is True
    assert "CPU" in chat["response"]

    command = post("/api/command", {"command": "Get-Date"})
    assert command["ok"] is True

    post("/api/memory", {"key": "selftest", "value": "ok"})
    assert get("/api/memory/selftest")["value"] == "ok"

    task = post(
        "/api/tasks",
        {
            "title": "selftest-task",
            "action": "memory:selftest_task=ok",
            "delay_seconds": 0,
        },
    )
    time.sleep(2)
    assert get("/api/memory/selftest_task")["value"] == "ok"
    delete(f"/api/tasks/{task['id']}")
    delete("/api/memory/selftest")
    delete("/api/memory/selftest_task")

    print("SELFTEST OK")


if __name__ == "__main__":
    main()
