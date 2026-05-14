@echo off
setlocal
cd /d "%~dp0"

set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8765 .*LISTENING"') do (
  set "FOUND=1"
  taskkill /PID %%P /F >nul 2>nul
)

if defined FOUND (
  echo JARVIS arrestato.
) else (
  echo Nessun server JARVIS in ascolto sulla porta 8765.
)
