@echo off
setlocal
cd /d "%~dp0"

set "PY313=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
set "RUNPY="

if exist ".venv313\Scripts\python.exe" (
  ".venv313\Scripts\python.exe" -c "import fastapi,uvicorn,psutil" >nul 2>nul
  if not errorlevel 1 set "RUNPY=.venv313\Scripts\python.exe"
)

if not defined RUNPY if exist "%PY313%" (
  "%PY313%" -c "import fastapi,uvicorn,psutil" >nul 2>nul
  if not errorlevel 1 set "RUNPY=%PY313%"
)

if not defined RUNPY if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import fastapi,uvicorn,psutil" >nul 2>nul
  if not errorlevel 1 set "RUNPY=.venv\Scripts\python.exe"
)

if not defined RUNPY (
  call install.bat
  if errorlevel 1 exit /b 1
)

if not defined RUNPY if exist ".venv313\Scripts\python.exe" set "RUNPY=.venv313\Scripts\python.exe"
if not defined RUNPY if exist "%PY313%" set "RUNPY=%PY313%"
if not defined RUNPY if exist ".venv\Scripts\python.exe" set "RUNPY=.venv\Scripts\python.exe"

if not defined RUNPY (
  echo Nessun Python valido trovato.
  exit /b 1
)

echo Avvio JARVIS su http://127.0.0.1:8765
"%RUNPY%" server.py
