#!/usr/bin/env python3
"""Quick script to check Telegram webhook status."""

import sys
import io

# Fix Windows encoding issues
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
try:
    import config
    BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
except ImportError:
    print("Error: config.py not found")
    sys.exit(1)

# Get webhook info from Telegram
url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
response = requests.get(url)
data = response.json()

if data.get("ok"):
    webhook_info = data.get("result", {})
    print("Current Webhook Status:")
    print(f"  URL: {webhook_info.get('url', 'Not set')}")
    print(f"  Pending updates: {webhook_info.get('pending_update_count', 0)}")
    print(f"  Last error date: {webhook_info.get('last_error_date', 'None')}")
    print(f"  Last error message: {webhook_info.get('last_error_message', 'None')}")
    
    current_url = webhook_info.get('url', '')
    if 'your-url.com' in current_url or not current_url or current_url == 'https://your-url.com/webhook':
        print("\n[WARNING] Webhook is set to placeholder URL!")
        print("You need to set it to a real URL (use ngrok or your public server)")
        print("\nTo set webhook with ngrok:")
        print("1. Start ngrok: ngrok http 8001")
        print("2. Copy the HTTPS URL (e.g., https://abc123.ngrok-free.app)")
        print("3. Run: curl \"http://localhost:8001/set_webhook?webhook_url=https://YOUR-NGROK-URL/webhook\"")
else:
    print(f"Error: {data.get('description', 'Unknown error')}")

