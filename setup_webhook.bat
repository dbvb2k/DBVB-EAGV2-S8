@echo off
REM Script to set Telegram webhook with ngrok URL
REM Usage: setup_webhook.bat YOUR_NGROK_URL
REM Example: setup_webhook.bat https://abc123.ngrok-free.app

if "%1"=="" (
    echo Usage: setup_webhook.bat YOUR_NGROK_URL
    echo Example: setup_webhook.bat https://abc123.ngrok-free.app
    echo.
    echo Or set it manually:
    echo curl "http://localhost:8001/set_webhook?webhook_url=https://YOUR-NGROK-URL/webhook"
    exit /b 1
)

set NGROK_URL=%1
set WEBHOOK_URL=%NGROK_URL%/webhook

echo Setting webhook to: %WEBHOOK_URL%
curl "http://localhost:8001/set_webhook?webhook_url=%WEBHOOK_URL%"
echo.
echo.
echo Verifying webhook...
python check_webhook.py

