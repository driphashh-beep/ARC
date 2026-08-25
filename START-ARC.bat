@echo off
setlocal
cd /d "%~dp0"
if not defined ARC_PORT set "ARC_PORT=3132"
if not defined ARC_ENV set "ARC_ENV=local"
if not defined ARC_PRIVACY_MODE set "ARC_PRIVACY_MODE=on"
if not defined ARC_MAX_OUTPUT_TOKENS set "ARC_MAX_OUTPUT_TOKENS=800"
if not defined ARC_MAX_TOOL_LOOPS set "ARC_MAX_TOOL_LOOPS=3"
if not defined ARC_DAILY_API_CALL_LIMIT set "ARC_DAILY_API_CALL_LIMIT=20"
if not defined ARC_DAILY_TOKEN_LIMIT set "ARC_DAILY_TOKEN_LIMIT=100000"
where python >nul 2>nul || (echo Python 3.10 or newer is required.& pause & exit /b 1)
python -c "import openai, discord" >nul 2>nul || python -m pip install -r requirements.txt
start "" "http://localhost:%ARC_PORT%"
python arc.py
if errorlevel 1 pause
