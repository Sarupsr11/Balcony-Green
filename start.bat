@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist logs mkdir logs

echo Killing any existing processes on ports 8000 and 8501...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /f /pid %%p >nul 2>&1
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8501 " ^| findstr "LISTENING"') do taskkill /f /pid %%p >nul 2>&1
taskkill /f /im cloudflared.exe >nul 2>&1

echo.
echo [1/3] Starting backend API...
if exist logs\api.log del /f /q logs\api.log
start "BG-API" /min cmd /c "python -m uvicorn balconygreen.auth_api:app --host 0.0.0.0 --port 8000 --app-dir src >> logs\api.log 2>&1"

echo Waiting for API to be ready...
:wait_api
timeout /t 1 /nobreak >nul
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 goto wait_api
echo  [OK] API ready on http://127.0.0.1:8000

echo.
echo [2/3] Starting Streamlit frontend...
if exist logs\ui.log del /f /q logs\ui.log
start "BG-UI" /min cmd /c "streamlit run src\balconygreen\app.py --server.port 8501 --server.headless true >> logs\ui.log 2>&1"

echo Waiting for Streamlit to be ready...
:wait_ui
timeout /t 1 /nobreak >nul
curl -s http://localhost:8501/_stcore/health >nul 2>&1
if errorlevel 1 goto wait_ui
echo  [OK] Streamlit ready on http://localhost:8501

echo.
echo [3/3] Starting Cloudflare Tunnel...
if exist logs\tunnel.log del /f /q logs\tunnel.log
start "BG-Tunnel" /min cmd /c "cloudflared tunnel --url http://localhost:8501 >> logs\tunnel.log 2>&1"

echo Waiting for tunnel URL...
set "TUNNEL_URL="
set /a TUNNEL_WAIT_SECONDS=0
:wait_tunnel
timeout /t 1 /nobreak >nul
set /a TUNNEL_WAIT_SECONDS+=1
set "TUNNEL_URL="
for /f "usebackq delims=" %%a in (`python -c "import pathlib,re,sys; p=pathlib.Path('logs/tunnel.log'); t=p.read_text(encoding='utf-8', errors='ignore') if p.exists() else ''; m=re.search(r'https://[\w-]+\.trycloudflare\.com', t); sys.stdout.write(m.group(0) if m else '')"`) do set "TUNNEL_URL=%%a"
if defined TUNNEL_URL goto tunnel_ready
if !TUNNEL_WAIT_SECONDS! geq 60 goto tunnel_timeout
goto wait_tunnel

:tunnel_timeout
set "TUNNEL_URL=URL not found (check logs\tunnel.log)"
echo  [WARN] Timed out waiting for the Cloudflare public URL.

:tunnel_ready

echo.
echo ============================================================
echo   Balcony Green is LIVE!
echo.
echo   Public URL : !TUNNEL_URL!
echo   Local UI   : http://localhost:8501
echo   Local API  : http://127.0.0.1:8000
echo ============================================================
echo.
echo Press any key to shut everything down...
pause >nul

echo Shutting down...
taskkill /f /fi "WINDOWTITLE eq BG-API*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq BG-UI*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq BG-Tunnel*" >nul 2>&1
taskkill /f /im cloudflared.exe >nul 2>&1
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /f /pid %%p >nul 2>&1
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8501 " ^| findstr "LISTENING"') do taskkill /f /pid %%p >nul 2>&1
echo Done.
