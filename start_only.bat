@echo off
setlocal

cd /d "%~dp0"

echo [1/3] Checking required tools...
where docker >nul 2>nul
if errorlevel 1 (
    echo Docker is not installed or not on PATH.
    exit /b 1
)

echo [2/3] Starting Docker Desktop if needed...
docker info >nul 2>nul
if errorlevel 1 (
    if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
        start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        echo Waiting for Docker to become ready...
        call :wait_for_docker
        if errorlevel 1 (
            echo Docker did not become ready in time.
            exit /b 1
        )
    ) else (
        echo Docker Desktop is not running and could not be started automatically.
        exit /b 1
    )
)

echo [3/3] Building and starting Balcony Green...
cd /d "%~dp0src\balconygreen"
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
if errorlevel 1 (
    echo Docker compose failed.
    exit /b 1
)

endlocal
exit /b 0

:wait_for_docker
for /l %%I in (1,1,36) do (
    docker info >nul 2>nul
    if not errorlevel 1 (
        exit /b 0
    )
    timeout /t 5 /nobreak >nul
)
exit /b 1
