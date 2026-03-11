@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   LAN File Browser - Stop Server
echo ============================================
echo.

:: Default port, change if you used --port to start
set PORT=25600

:: Allow user to specify port as argument: stop_server.bat 8080
if not "%~1"=="" set PORT=%~1

echo [1/3] Searching for process on port %PORT%...
set PID=
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    set PID=%%a
)

if "%PID%"=="" (
    echo.
    echo [OK] No process found on port %PORT%. Server is not running.
    echo.
    pause
    exit /b 0
)

echo Found process PID: %PID%
echo.

echo [2/3] Process details:
tasklist /FI "PID eq %PID%" 2>nul
echo.

echo [3/3] Stopping process...
taskkill /PID %PID% /F >nul 2>&1

if !errorlevel! equ 0 (
    echo.
    echo [OK] Server stopped successfully! PID: %PID%
) else (
    echo.
    echo [ERROR] Failed to stop. Try running as Administrator.
)

echo.
pause
