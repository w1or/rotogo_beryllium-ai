@echo off
rem ============================================================
rem  RotoGo Beryllium v7.1 - start WITHOUT a console window.
rem  ASCII-only file: no garbled names in Windows Explorer.
rem ============================================================

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0rotogo.pyw"
    exit /b 0
)

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3 "%~dp0rotogo.pyw"
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    rem fallback: a console flashes for a moment, then the app
    rem detaches itself from it (closing cmd will not close the app)
    start "" /min python "%~dp0rotogo.pyw"
    exit /b 0
)

echo Python not found! Install it from https://www.python.org/downloads/
echo (check "Add python.exe to PATH" during installation)
pause
