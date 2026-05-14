@echo off
setlocal
cd /d "%~dp0"

call install.bat
if errorlevel 1 exit /b 1

set "RUNPY=.venv313\Scripts\python.exe"
if not exist "%RUNPY%" set "RUNPY=.venv\Scripts\python.exe"

netstat -ano | findstr /R /C:":8765 .*LISTENING" >nul
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%RUNPY%' -ArgumentList 'server.py' -WorkingDirectory '%CD%' -WindowStyle Hidden"
  timeout /t 2 /nobreak >nul
)

start "" "http://127.0.0.1:8765"
echo JARVIS operativo: http://127.0.0.1:8765
