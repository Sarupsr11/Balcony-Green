@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Balcony Green - Flash ESP32

cls
echo.
echo  ============================================================
echo    Balcony Green - ESP32 Setup ^& Flash
echo  ============================================================
echo.
echo  This tool will automatically:
echo    1. Start the Balcony Green server
echo    2. Detect your local network IP
echo    3. Generate a fresh login token
echo    4. Update the ESP32 firmware with your settings
echo    5. Flash your ESP32 (or open Arduino IDE if needed)
echo.
echo  BEFORE YOU START:
echo    - Connect your ESP32 to this PC via USB
echo    - Make sure your phone hotspot is ON
echo    - Connect THIS laptop to the phone hotspot
echo  ============================================================
echo.
pause

cls
echo.
echo  STEP 1 of 3 - Enter your Hotspot details
echo  -----------------------------------------
echo  (These must match your phone hotspot exactly)
echo.
set "HOTSPOT_SSID=Myphone"
set "HOTSPOT_PASS=12345678"
set /p "HOTSPOT_SSID=  Hotspot name (default: Myphone): "
if "!HOTSPOT_SSID!"=="" set "HOTSPOT_SSID=Myphone"
set /p "HOTSPOT_PASS=  Hotspot password (default: 12345678): "
if "!HOTSPOT_PASS!"=="" set "HOTSPOT_PASS=12345678"

echo.
echo  Got it! SSID: !HOTSPOT_SSID!
echo.

:: ── Start backend API ─────────────────────────────────────────
echo  Starting Balcony Green server...
if not exist logs mkdir logs
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 (
    start "BG-API" /min cmd /c "cd /d "%~dp0" && python -m uvicorn balconygreen.auth_api:app --host 0.0.0.0 --port 8000 --app-dir src >> logs\api.log 2>&1"
    :wait_api
    timeout /t 1 /nobreak >nul
    curl -s http://127.0.0.1:8000/health >nul 2>&1
    if errorlevel 1 goto wait_api
)
echo  Server is running!
echo.

:: ── Detect local IP ───────────────────────────────────────────
echo  Detecting your local IP on the hotspot network...
for /f "delims=" %%i in ('python -c "import socket; s=socket.socket(); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2^>nul') do set "LOCAL_IP=%%i"
if "!LOCAL_IP!"=="" (
    echo.
    echo  Could not detect your IP automatically.
    echo  Make sure this laptop is connected to your phone hotspot, then:
    set /p "LOCAL_IP=  Type your IP address manually: "
)
echo  Your IP address: !LOCAL_IP!
echo.

:: ── Get fresh JWT ─────────────────────────────────────────────
echo  Generating a fresh login token...
for /f "delims=" %%t in ('python -c "import requests,sys; r=requests.post('http://127.0.0.1:8000/auth/login', json={'username':'balconygreen','password':'balconygreen'}, timeout=5); sys.stdout.write(r.json().get('access_token',''))" 2^>nul') do set "JWT_TOKEN=%%t"
if "!JWT_TOKEN!"=="" (
    echo.
    echo  ERROR: Could not get a login token.
    echo  Make sure the server started correctly (check logs\api.log)
    echo.
    pause
    exit /b 1
)
echo  Login token generated!
echo.

:: ── Patch .ino ────────────────────────────────────────────────
echo  Updating ESP32 firmware with your settings...
set "INO_PATH=examples\esp32_water_now_demo\esp32_water_now_demo.ino"
python -c ^"
import re
path = r'%INO_PATH%'
with open(path, 'r', encoding='utf-8') as f:
    src = f.read()
src = re.sub(r'const char\* WIFI_SSID\s*=\s*\"[^\"]*\"',     f'const char* WIFI_SSID = \"%HOTSPOT_SSID%\"',               src)
src = re.sub(r'const char\* WIFI_PASSWORD\s*=\s*\"[^\"]*\"', f'const char* WIFI_PASSWORD = \"%HOTSPOT_PASS%\"',            src)
src = re.sub(r'const char\* API_BASE_URL\s*=\s*\"[^\"]*\"',  f'const char* API_BASE_URL = \"http://%LOCAL_IP%:8000\"',     src)
src = re.sub(r'const char\* JWT_TOKEN\s*=\s*\"[^\"]*\"',     f'const char* JWT_TOKEN = \"!JWT_TOKEN!\"',                   src)
with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
^"
if errorlevel 1 (
    echo  ERROR: Could not update the firmware file.
    pause
    exit /b 1
)
echo  Firmware updated!
echo.

cls
echo.
echo  STEP 2 of 3 - Detecting your ESP32
echo  ------------------------------------
echo  Make sure the ESP32 is plugged in via USB now.
echo.
pause

for /f "delims=" %%p in ('python -c ^"
import serial.tools.list_ports, sys
keywords = ['CP210', 'CH340', 'CH341', 'FTDI', 'USB Serial', 'USB-SERIAL', 'Silicon Labs']
for p in serial.tools.list_ports.comports():
    desc = (p.description or '') + (p.manufacturer or '')
    if any(k.lower() in desc.lower() for k in keywords):
        sys.stdout.write(p.device); sys.exit(0)
all_ports = list(serial.tools.list_ports.comports())
if all_ports: sys.stdout.write(all_ports[0].device)
^" 2^>nul') do set "COM_PORT=%%p"

if "!COM_PORT!"=="" (
    echo  Could not find your ESP32 automatically.
    echo  Open Device Manager and look under "Ports (COM ^& LPT)" for the COM number.
    echo.
    set /p "COM_PORT=  Enter your COM port (e.g. COM3): "
)
echo  Found ESP32 on port: !COM_PORT!
echo.

cls
echo.
echo  STEP 3 of 3 - Flashing the ESP32
echo  -----------------------------------

where arduino-cli >nul 2>&1
if errorlevel 1 (
    echo  arduino-cli not found - installing it now...
    echo  ^(This only happens once^)
    echo.
    powershell -Command "& { $url='https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip'; $zip='%TEMP%\arduino-cli.zip'; $dest='%LOCALAPPDATA%\arduino-cli'; Invoke-WebRequest $url -OutFile $zip; Expand-Archive $zip -DestinationPath $dest -Force; [Environment]::SetEnvironmentVariable('PATH', $env:PATH + ';' + $dest, 'User') }" >nul 2>&1
    set "PATH=%PATH%;%LOCALAPPDATA%\arduino-cli"
    where arduino-cli >nul 2>&1
    if errorlevel 1 (
        echo  Auto-install failed. Opening Arduino IDE instead.
        goto open_ide
    )
    echo  arduino-cli installed successfully!
    echo.
)

echo  arduino-cli ready! Compiling and flashing automatically...
echo.
echo  Installing ESP32 board support ^(first run may take a minute^)...
arduino-cli config init --overwrite >nul 2>&1
arduino-cli config add board_manager.additional_urls https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json >nul 2>&1
arduino-cli core update-index >nul 2>&1
arduino-cli core install esp32:esp32 >nul 2>&1
echo  Compiling firmware...
arduino-cli compile --fqbn esp32:esp32:esp32 "%INO_PATH%"
if errorlevel 1 (
    echo.
    echo  Compile failed. Opening Arduino IDE instead - please flash manually.
    goto open_ide
)
echo  Flashing to !COM_PORT! ...
arduino-cli upload --fqbn esp32:esp32:esp32 --port !COM_PORT! "%INO_PATH%"
if errorlevel 1 (
    echo.
    echo  Flash failed. Opening Arduino IDE instead - please flash manually.
    goto open_ide
)
goto flash_done

:open_ide
echo  Opening the firmware in Arduino IDE for you to flash manually.
echo.
echo  In Arduino IDE:
echo    1. Go to Tools ^> Board ^> ESP32 Arduino ^> ESP32 Dev Module
echo    2. Go to Tools ^> Port ^> !COM_PORT!
echo    3. Click the Upload button (arrow icon)
echo.
start "" "%INO_PATH%"
pause
goto summary

:flash_done
echo  Flash complete!

:summary
cls
echo.
echo  ============================================================
echo    All done! Here is your setup summary:
echo  ============================================================
echo.
echo    Hotspot name   : !HOTSPOT_SSID!
echo    Server IP      : !LOCAL_IP!:8000
echo    ESP32 port     : !COM_PORT!
echo    Dashboard      : http://!LOCAL_IP!:8501
echo.
echo  What to do next:
echo    1. Unplug the USB cable from the ESP32
echo    2. Power the ESP32 from a USB charger or powerbank
echo    3. Make sure your phone hotspot stays ON
echo    4. Open the dashboard in your browser:
echo       http://!LOCAL_IP!:8501
echo    5. Go to ESP32 Device Management and register your device
echo.
echo  ============================================================
echo.
pause
