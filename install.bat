@echo off
setlocal
cd /d "%~dp0"

set "PY313=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
set "VENV=.venv313"

if exist "%VENV%\Scripts\python.exe" (
  "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto fail
  goto ok
)

if exist "%PY313%" (
  if not exist "%VENV%\Scripts\python.exe" (
    "%PY313%" -m venv "%VENV%"
    if errorlevel 1 goto fail
  )
  "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto fail
  goto ok
)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto fail
    goto ok
  )
)

if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
  if errorlevel 1 goto fail
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail

:ok
echo.
echo jERVIS installato correttamente.
echo Avvio: start.bat
exit /b 0

:fail
echo.
echo Installazione fallita. Verifica che Python Launcher "py" sia installato.
exit /b 1
