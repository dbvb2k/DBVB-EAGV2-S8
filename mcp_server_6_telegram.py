# mcp_server_6_telegram.py - Telegram Bot MCP Server (SSE Transport)

import sys
import os
import asyncio
import json
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from typing import List, Optional
import requests

# Fix encoding issues on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Import config
try:
    import config
except ImportError:
    print("Warning: config.py not found. Please create it with required settings.")
    sys.exit(1)

mcp = FastMCP("telegram")


# Pydantic models for tool I/O
class SendTelegramMessageInput(BaseModel):
    chat_id: str
    message: str
    parse_mode: str = "HTML"  # HTML or Markdown


class SendTelegramMessageOutput(BaseModel):
    message_id: int
    status: str


class TelegramMessageData(BaseModel):
    chat_id: str
    text: str
    message_id: int


# Telegram Bot API base URL
TELEGRAM_API_URL = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


@mcp.tool()
def send_telegram_message(input: SendTelegramMessageInput) -> SendTelegramMessageOutput:
    """
    Send a message via Telegram bot.
    
    Args:
        input: SendTelegramMessageInput with chat_id, message, and parse_mode
        
    Returns:
        SendTelegramMessageOutput with message_id and status
    """
    print(f"CALLED: send_telegram_message to chat: {input.chat_id}")
    
    try:
        url = f"{TELEGRAM_API_URL}/sendMessage"
        
        payload = {
            "chat_id": input.chat_id,
            "text": input.message,
            "parse_mode": input.parse_mode
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("ok"):
            message_id = result["result"]["message_id"]
            print(f"[SUCCESS] Telegram message sent. Message ID: {message_id}")
            
            return SendTelegramMessageOutput(
                message_id=message_id,
                status="sent"
            )
        else:
            error_msg = result.get("description", "Unknown error")
            raise Exception(f"Telegram API error: {error_msg}")
    
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Error sending Telegram message: {e}")
        raise Exception(f"Failed to send Telegram message: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        raise Exception(f"Failed to send Telegram message: {e}")


@mcp.tool()
def get_telegram_updates(last_update_id: Optional[int] = 0) -> str:
    """
    Get latest updates from Telegram (messages, etc.).
    
    Args:
        last_update_id: The last update ID you've processed (optional)
        
    Returns:
        JSON string with updates
    """
    print(f"CALLED: get_telegram_updates since update_id: {last_update_id}")
    
    try:
        url = f"{TELEGRAM_API_URL}/getUpdates"
        
        params = {
            "offset": last_update_id + 1 if last_update_id else None,
            "timeout": 10
        }
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("ok"):
            updates = result.get("result", [])
            print(f"[SUCCESS] Retrieved {len(updates)} updates from Telegram")
            
            return json.dumps(updates, indent=2)
        else:
            error_msg = result.get("description", "Unknown error")
            raise Exception(f"Telegram API error: {error_msg}")
    
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Error getting Telegram updates: {e}")
        raise Exception(f"Failed to get Telegram updates: {e}")


@mcp.tool()
def send_telegram_reply(chat_id: str, reply_to_message_id: int, message: str) -> SendTelegramMessageOutput:
    """
    Send a reply to a specific Telegram message.
    
    Args:
        chat_id: The chat ID to reply in
        reply_to_message_id: The message ID to reply to
        message: The reply message text
        
    Returns:
        SendTelegramMessageOutput with message_id and status
    """
    print(f"CALLED: send_telegram_reply in chat: {chat_id}")
    
    try:
        url = f"{TELEGRAM_API_URL}/sendMessage"
        
        payload = {
            "chat_id": chat_id,
            "text": message,
            "reply_to_message_id": reply_to_message_id,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("ok"):
            message_id = result["result"]["message_id"]
            print(f"[SUCCESS] Telegram reply sent. Message ID: {message_id}")
            
            return SendTelegramMessageOutput(
                message_id=message_id,
                status="sent"
            )
        else:
            error_msg = result.get("description", "Unknown error")
            raise Exception(f"Telegram API error: {error_msg}")
    
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Error sending Telegram reply: {e}")
        raise Exception(f"Failed to send Telegram reply: {e}")


@mcp.resource("telegram://chat/{chat_id}")
def get_chat_info(chat_id: str) -> str:
    """Get information about a Telegram chat."""
    try:
        url = f"{TELEGRAM_API_URL}/getChat"
        params = {"chat_id": chat_id}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("ok"):
            return json.dumps(result["result"], indent=2)
        else:
            return f"Error: {result.get('description', 'Unknown error')}"
    
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    print("Starting Telegram MCP Server (SSE)...")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Development mode
    else:
        # Run with SSE transport
        port = int(os.getenv("SSE_PORT", config.SSE_PORT)) + 2
        # Update settings for host and port
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = port
        print(f"Server will run on http://127.0.0.1:{port}")
        mcp.run(transport="sse")
        print(f"\nServer running on http://127.0.0.1:{port}")
        print("Shutting down...")

