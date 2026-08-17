@echo off
setlocal EnableExtensions

title RL Agent - Local Startup

set "ROOT_DIR=%~dp0"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"
set "MONGO_URI=mongodb://127.0.0.1:27017"

echo ============================================================
echo  RL AGENT - WINDOWS LOCAL START
echo ============================================================

cd /d "%ROOT_DIR%"

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found.
    echo Install Python 3 and try again.
    pause
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm was not found.
    echo Install Node.js/npm and try again.
    pause
    exit /b 1
)

if not exist "frontend\package.json" (
    echo ERROR: frontend\package.json not found.
    pause
    exit /b 1
)

if not exist "backend\main.py" (
    echo ERROR: backend\main.py not found.
    pause
    exit /b 1
)

echo.
echo [1] Checking frontend dependencies...

if not exist "frontend\node_modules\.bin\vite.cmd" (
    echo Vite not found.

    if exist "frontend\package-lock.json" (
        echo Running npm ci...
        cd /d "%ROOT_DIR%frontend"
        call npm ci

        if errorlevel 1 (
            echo ERROR: npm ci failed.
            pause
            exit /b 1
        )

        cd /d "%ROOT_DIR%"
    ) else (
        echo Running npm install...
        cd /d "%ROOT_DIR%frontend"
        call npm install

        if errorlevel 1 (
            echo ERROR: npm install failed.
            pause
            exit /b 1
        )

        cd /d "%ROOT_DIR%"
    )
) else (
    echo Frontend dependencies already installed.
)

if not exist "frontend\node_modules\.bin\vite.cmd" (
    echo ERROR: Vite is still unavailable.
    pause
    exit /b 1
)

echo.
echo [2] Starting backend...

set "MONGO_URI=%MONGO_URI%"
set "DATABASE_NAME=soar_rl_agent"
set "PYTHONPATH=%ROOT_DIR%backend;%ROOT_DIR%"

start "RL Agent Backend" cmd /k ^
    "cd /d ""%ROOT_DIR%"" && set MONGO_URI=%MONGO_URI% && set DATABASE_NAME=soar_rl_agent && set PYTHONPATH=%ROOT_DIR%backend;%ROOT_DIR% && python -m uvicorn backend.main:app --host 127.0.0.1 --port %BACKEND_PORT%"

echo Backend launch requested.

echo.
echo [3] Starting frontend...

start "RL Agent Frontend" cmd /k ^
    "cd /d ""%ROOT_DIR%frontend"" && npm run dev -- --host 0.0.0.0 --port %FRONTEND_PORT%"

echo Frontend launch requested.

echo.
echo ============================================================
echo  RL AGENT START COMMANDS SENT
echo ============================================================
echo Backend : http://127.0.0.1:%BACKEND_PORT%
echo Frontend: http://127.0.0.1:%FRONTEND_PORT%
echo MongoDB : %MONGO_URI%
echo.
echo Backend and frontend run in separate command windows.
echo ============================================================

pause
