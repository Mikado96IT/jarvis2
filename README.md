# JARVIS — Iron Man Autonomous System

Sistema AI locale con HUD web, runtime autonomo continuo, scheduler, memoria SQLite, tool engine sicuro, controllo PC, voce browser e integrazione Ollama.

## Avvio

```bat
launch.bat
```

Apri `http://127.0.0.1:8765`.

## Comandi

```bat
launch.bat    # installa, avvia in background e apre il browser
start.bat     # avvia in foreground nella finestra corrente
stop.bat      # arresta il server sulla porta 8765
```

PowerShell senza alias `python`:

```powershell
.\.venv313\Scripts\python.exe server.py
```

## Architettura

- `core/`: brain Ollama, fallback locale, loop agente, orchestrazione tool.
- `voice/`: wake word, pipeline transcript, TTS locale via pyttsx3 o Windows Speech.
- `tools/`: file, comandi, app launcher, Python execution, process/system monitor.
- `memory/`: SQLite persistente per memoria, conversazioni, eventi, task e storico.
- `scheduler/`: runtime continuo, task time-based/ricorrenti, monitor sistema.
- `api/`: schemi e contratti dell'API interna.
- `app/`: server FastAPI e wiring dei moduli.
- `web/`: HUD Iron Man responsive con chat, voce, task, memoria, metriche e log.

## AI locale

JARVIS tenta di usare Ollama su `http://127.0.0.1:11434` con modello `llama3.2`.
Se Ollama non è attivo, il sistema resta funzionante con fallback locale operativo.

Per attivare il brain LLM:

```bat
ollama.bat pull llama3.2
ollama.bat serve
```

Poi riavvia JARVIS.

Se Ollama non è installato e non hai un package manager:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_ollama.ps1
```

## Voce

Nel browser premi `◉` per ascolto continuo o `▣` per push-to-talk.
Wake word: `JARVIS`.

Esempi:

- `Jarvis stato sistema`
- `Jarvis esegui comando Get-Date`
- `Jarvis ricorda nome=Michael`

## Tool console

Comandi consentiti configurati in `config/settings.json`.
Azioni distruttive o fuori allowlist richiedono conferma esplicita.

## Scheduler

Azioni supportate:

- `agent:stato sistema`
- `command:Get-Date`
- `python:print("ok")`
- `url:https://example.com`
- `app:notepad`
- `memory:chiave=valore`

## Self-test

Con JARVIS avviato:

```bat
.\.venv313\Scripts\python.exe scripts\selftest.py
```
