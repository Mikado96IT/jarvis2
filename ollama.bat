@echo off
setlocal
set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"

if not exist "%OLLAMA_EXE%" (
  echo Ollama non trovato in "%OLLAMA_EXE%".
  echo Riavvia il terminale o reinstalla Ollama.
  exit /b 1
)

"%OLLAMA_EXE%" %*
