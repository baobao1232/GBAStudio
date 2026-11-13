@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py
) else (
  echo GBA Studio has not been installed yet.
  echo Run INSTALL.bat first.
  pause
  exit /b 1
)
if errorlevel 1 pause
