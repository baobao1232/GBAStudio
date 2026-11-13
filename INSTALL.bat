@echo off
setlocal
cd /d "%~dp0"
set "PYEXE="

REM Prefer the common per-user Python 3.12 installation path.
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set PYEXE="%LocalAppData%\Programs\Python\Python312\python.exe"

REM Then try the Python launcher.
if not defined PYEXE (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3.12 --version >nul 2>nul
    if not errorlevel 1 set "PYEXE=py -3.12"
  )
)

REM Last fallback: locate a real python.exe, skipping the Microsoft Store alias.
if not defined PYEXE (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | findstr /i /c:"\WindowsApps\" >nul
    if errorlevel 1 if not defined PYEXE set PYEXE="%%P"
  )
)

if not defined PYEXE (
  echo Python 3.12 64-bit was not found.
  echo Install it from https://www.python.org/downloads/windows/
  echo Enable Add Python to PATH, then run this installer again.
  pause
  exit /b 1
)

%PYEXE% --version
if errorlevel 1 goto :fail
%PYEXE% -m venv .venv
if errorlevel 1 goto :fail
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :fail
echo.
echo Installation complete. Run GBAStudio.bat.
pause
exit /b 0
:fail
echo Installation failed. Check Python 3.12 and your internet connection.
pause
exit /b 1
