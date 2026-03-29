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

:: Extract local address (column 2) and PID (column 5) from LISTENING lines
:: Then check if the local address ends with :%PORT% to avoid substring matches
for /f "tokens=2,5" %%a in ('netstat -ano 2^>nul ^| findstr "LISTENING"') do (
    echo %%a | findstr /E ":%PORT%" >nul 2>&1
    if !errorlevel! equ 0 set PID=%%b
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

:: 先尝试优雅终止（不带 /F）
taskkill /PID %PID% >nul 2>&1
if !errorlevel! equ 0 (
    echo Waiting for graceful shutdown...
    timeout /t 3 /nobreak >nul 2>&1

    :: 检查进程是否仍在运行
    tasklist /FI "PID eq %PID%" 2>nul | findstr /I "%PID%" >nul 2>&1
    if !errorlevel! equ 0 (
        echo Process still running, force killing...
        taskkill /PID %PID% /F >nul 2>&1
    )
)

:: 最终确认
tasklist /FI "PID eq %PID%" 2>nul | findstr /I "%PID%" >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo [OK] Server stopped successfully! PID: %PID%
) else (
    echo.
    echo [ERROR] Failed to stop. Try running as Administrator.
)

echo.
pause
