@echo off
setlocal
title First Issue GraphRAG - Stop Servers

echo ============================================================
echo   First Issue GraphRAG - Stop Backend + Frontend
echo ============================================================
echo.

set "BACKEND_PORT=8090"
set "FRONTEND_PORT=3000"
set "STOPPED=0"

echo Stopping anything on port %BACKEND_PORT% (backend) ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /T /PID %%a >nul 2>&1 && ( echo   [OK] stopped backend  PID %%a & set "STOPPED=1" )
)

echo Stopping anything on port %FRONTEND_PORT% (frontend) ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /T /PID %%a >nul 2>&1 && ( echo   [OK] stopped frontend PID %%a & set "STOPPED=1" )
)

echo.
if "%STOPPED%"=="1" (
    echo   Done - both ports cleared.
) else (
    echo   Nothing was listening on %BACKEND_PORT% or %FRONTEND_PORT%.
)
echo ============================================================
echo.
pause
endlocal
