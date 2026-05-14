from __future__ import annotations

import re


class WakeWordDetector:
    def __init__(self, wake_word: str = "jarvis"):
        self.wake_word = wake_word.lower().strip()

    def detect(self, transcript: str) -> dict[str, str | bool]:
        text = transcript.strip()
        normalized = re.sub(r"\s+", " ", text.lower())
        if self.wake_word not in normalized:
            return {"active": False, "command": "", "transcript": text}
        command = re.sub(re.escape(self.wake_word), "", normalized, count=1).strip(" ,.:;")
        return {"active": True, "command": command, "transcript": text}
