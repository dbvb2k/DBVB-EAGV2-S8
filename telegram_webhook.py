# telegram_webhook.py - Telegram Webhook Handler with Agent Integration

import asyncio
import os
import sys
import json
import yaml
import requests
from datetime import datetime
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.loop import AgentLoop
from core.session import MultiMCP

# Import config
try:
    import config
except ImportError:
    print("Error: config.py not found. Please create it with required settings.")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram Agent Webhook")

# Telegram Bot API
TELEGRAM_API_URL = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def log(stage: str, msg: str):
    """Simple timestamped logger."""
    now = datetime.now().strftime("%H:%M:%S")
    logger.info(f"[{now}] [{stage}] {msg}")


def send_telegram_message(chat_id: str, message: str, parse_mode: str = "HTML") -> bool:
    """Send a message via Telegram."""
    try:
        url = f"{TELEGRAM_API_URL}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": parse_mode
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json().get("ok", False)
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


async def process_query_with_agent(query: str, chat_id: str) -> str:
    """
    Process a user query using the Agent Loop.
    
    Returns the agent's final answer.
    """
    try:
        # Send "thinking" message
        send_telegram_message(chat_id, "🤔 Processing your query...")
        
        # Load MCP server configs from profiles.yaml
        with open("config/profiles.yaml", "r") as f:
            profile = yaml.safe_load(f)
            mcp_servers = profile.get("mcp_servers", [])
        
        # Initialize MultiMCP
        multi_mcp = MultiMCP(server_configs=mcp_servers)
        await multi_mcp.initialize()
        
        log("agent", f"Initialized MultiMCP with {len(multi_mcp.get_all_tools())} tools")
        
        # Run agent loop
        agent = AgentLoop(
            user_input=query,
            dispatcher=multi_mcp
        )
        
        try:
            final_response = await agent.run()
            # Extract final answer from FINAL_ANSWER: prefix
            answer = final_response.replace("FINAL_ANSWER:", "").strip()
            log("agent", f"Agent completed: {answer[:100]}...")
            return answer
        
        except Exception as e:
            log("error", f"Agent failed: {e}")
            return f"Sorry, I encountered an error: {str(e)}"
    
    except Exception as e:
        log("error", f"Failed to process query: {e}")
        return f"Sorry, I encountered an error: {str(e)}"


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "Telegram Agent Webhook"}


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "service": "Telegram Agent Webhook",
        "telegram_configured": bool(config.TELEGRAM_BOT_TOKEN),
        "gmail_configured": bool(config.SENDER_EMAIL and config.RECEIVER_EMAIL),
        "google_sheets_configured": os.path.exists(config.GOOGLE_CREDENTIALS_PATH)
    }


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram webhook updates."""
    try:
        data = await request.json()
        
        # Log the update
        log("webhook", f"Received update: {json.dumps(data, indent=2)[:200]}")
        
        # Extract message data
        if "message" not in data:
            return Response(status_code=200)  # Not a message, ignore
        
        message = data["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        message_id = message["message_id"]
        
        # Handle bot commands
        if text.startswith("/start"):
            welcome_msg = """
🤖 <b>Welcome to the Agentic AI Assistant!</b>

Send me a query and I'll:
1️⃣ Process your request using my tools
2️⃣ Store results in a Google Sheet
3️⃣ Email you the sheet link

Try: <i>"Find the Current Point Standings of F1 Racers"</i>
            """
            send_telegram_message(str(chat_id), welcome_msg)
            return Response(status_code=200)
        
        if text.startswith("/help"):
            help_msg = """
📋 <b>Available Commands:</b>

• /start - Start the bot
• /help - Show this help message
• Send any query - I'll process it and email you results

<b>Example queries:</b>
• Find the Current Point Standings of F1 Racers
• What's the weather in New York?
• Search for AI trends in 2024
            """
            send_telegram_message(str(chat_id), help_msg)
            return Response(status_code=200)
        
        # Ignore empty messages
        if not text or len(text.strip()) == 0:
            return Response(status_code=200)
        
        # Process the query asynchronously
        try:
            # Run agent in background
            answer = await process_query_with_agent(text, str(chat_id))
            
            # Send the result
            if answer:
                send_telegram_message(str(chat_id), f"✅ <b>Result:</b>\n\n{answer}")
            else:
                send_telegram_message(str(chat_id), "❌ Sorry, I couldn't process your query.")
        
        except Exception as e:
            log("error", f"Error processing query: {e}")
            send_telegram_message(str(chat_id), f"❌ Sorry, an error occurred: {str(e)}")
        
        return Response(status_code=200)
    
    except Exception as e:
        log("error", f"Webhook error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/set_webhook")
async def set_webhook(webhook_url: str):
    """Manually set the Telegram webhook URL."""
    try:
        url = f"{TELEGRAM_API_URL}/setWebhook"
        payload = {"url": webhook_url}
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result.get("ok"):
            return {"status": "success", "message": "Webhook set successfully"}
        else:
            return {"status": "error", "message": result.get("description")}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    
    port = config.TELEGRAM_WEBHOOK_PORT
    log("startup", f"Starting Telegram Webhook server on port {port}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

