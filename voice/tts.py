from __future__ import annotations

import os
import subprocess
import threading
from typing import Any

from memory import MemoryStore


class VoiceEngine:
    def __init__(self, settings: dict[str, Any], store: MemoryStore):
        self.settings = settings
        self.store = store
        self.enabled = bool(settings.get("voice", {}).get("tts_enabled", True))

    def speak(self, text: str) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "TTS disabilitato"}
        clean = text.strip()
        if not clean:
            return {"ok": False, "error": "Testo mancante"}
        threading.Thread(target=self._speak_sync, args=(clean,), daemon=True).start()
        return {"ok": True, "text": clean}

    def _speak_sync(self, text: str) -> None:
        try:
            try:
                import pyttsx3  # type: ignore

                engine = pyttsx3.init()
                engine.setProperty("rate", int(self.settings.get("voice", {}).get("tts_rate", 175)))
                engine.say(text)
                engine.runAndWait()
                return
            except Exception:
                pass

            if os.name == "nt":
                escaped = text.replace("'", "''")
                command = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.Rate = 0; $s.Speak('{escaped}')"
                )
                subprocess.run(["powershell", "-NoProfile", "-Command", command], check=False, timeout=30)
            else:
                subprocess.run(["say", text], check=False, timeout=30)
        except Exception as exc:  # noqa: BLE001
            self.store.log_event("error", "TTS fallito", {"error": str(exc)})
