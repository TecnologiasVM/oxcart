@echo off
setlocal EnableDelayedExpansion
title First Issue GraphRAG - Init Servers

echo ============================================================
echo   First Issue GraphRAG - Start Backend + Frontend
echo ============================================================
echo.

REM --- Paths resolved relative to THIS script (first_issue_graphrag\) ---
set "APP_DIR=%~dp0"
set "VENV_PY=%APP_DIR%..\.venv-clean\Scripts\python.exe"
set "BACKEND_DIR=%APP_DIR%backend"
set "FRONTEND_DIR=%APP_DIR%frontend"
set "BACKEND_PORT=8090"
set "FRONTEND_PORT=3000"

REM --- Sanity checks ---
if not exist "%VENV_PY%" (
    echo   [ERROR] .venv-clean not found at:
    echo           "%VENV_PY%"
    echo           Expected the project venv at the repo root ^(^<repo^>\.venv-clean^).
    pause & exit /b 1
)
if not exist "%BACKEND_DIR%\app\main.py" (
    echo   [ERROR] backend not found at "%BACKEND_DIR%"
    pause & exit /b 1
)
if not exist "%FRONTEND_DIR%\package.json" (
    echo   [ERROR] frontend not found at "%FRONTEND_DIR%"
    pause & exit /b 1
)

REM --- Warn if .env.local would break remote (ZeroTier) access ---
echo [1/4] Checking frontend\.env.local ...
if exist "%FRONTEND_DIR%\.env.local" (
    findstr /r /c:"^NEXT_PUBLIC_API_BASE=." "%FRONTEND_DIR%\.env.local" >nul 2>&1
    if !errorlevel! == 0 (
        echo   [WARN] NEXT_PUBLIC_API_BASE is SET to a value in .env.local.
        echo          For LAN/ZeroTier this MUST be empty, i.e. the line should be exactly:
        echo              NEXT_PUBLIC_API_BASE=
        echo          Otherwise a phone/remote device tries to reach ITS OWN localhost
        echo          and the backend looks "disconnected". Fix it, then re-run this.
    ) else (
        echo   [OK] NEXT_PUBLIC_API_BASE is empty ^(remote devices will use the /api proxy^).
    )
) else (
    echo   [INFO] no .env.local found ^(defaults are fine: relative /api + 127.0.0.1:8090^).
)
echo.

REM --- Stop anything already bound to our ports (surgical: by port, not by image) ---
echo [2/4] Stopping anything on ports %BACKEND_PORT% and %FRONTEND_PORT% ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /T /PID %%a >nul 2>&1 && echo   [OK] stopped old backend  PID %%a
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /T /PID %%a >nul 2>&1 && echo   [OK] stopped old frontend PID %%a
)
echo   [INFO] ports cleared
echo.

REM --- Start BACKEND in its own window (FastAPI via .venv-clean, localhost only) ---
echo [3/4] Starting BACKEND  (FastAPI, .venv-clean, 127.0.0.1:%BACKEND_PORT%) ...
start "First Issue Backend (%BACKEND_PORT%)" /D "%BACKEND_DIR%" cmd /k ""%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT%"
echo   [OK] backend window launched
echo.

REM --- Start FRONTEND in its own window (Next.js dev, all interfaces incl. ZeroTier) ---
echo [4/4] Starting FRONTEND (Next.js dev, 0.0.0.0:%FRONTEND_PORT%) ...
start "First Issue Frontend (%FRONTEND_PORT%)" /D "%FRONTEND_DIR%" cmd /k "npm run dev"
echo   [OK] frontend window launched
echo.

echo ============================================================
echo   Servers starting (each in its own window)
echo ============================================================
echo   Backend health : http://127.0.0.1:%BACKEND_PORT%/api/health   (internal)
echo   Frontend local : http://localhost:%FRONTEND_PORT%/
echo.
echo   Open the FRONTEND from another device over ZeroTier/LAN using
echo   this machine's IP, e.g.:  http://ZEROTIER_IP:%FRONTEND_PORT%/
echo   The backend stays on localhost; the frontend proxies /api to it,
echo   so you do NOT expose port %BACKEND_PORT%.
echo.
echo   This machine's IPv4 addresses (use your ZeroTier 10.x one):
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /i "IPv4"') do echo       http://%%i:%FRONTEND_PORT%/
echo.
echo   To verify the whole chain from this machine:
echo       curl http://localhost:%FRONTEND_PORT%/api/health
echo   (should return JSON with neo4j/weaviate true)
echo ============================================================
echo.
echo   Prereqs: Neo4j + Weaviate must be running (docker).
echo   To stop: close the two server windows (or Ctrl+C in each).
echo.
pause
endlocal
