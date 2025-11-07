# telegram_webhook.py - Telegram Webhook Handler with Agent Integration

import asyncio
import os
import sys
import json
import yaml
import requests
import httpx
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

# Track processed update IDs to prevent duplicate processing
processed_updates = set()
MAX_PROCESSED_UPDATES = 1000  # Limit memory usage

# Bot user ID (will be set during startup)
BOT_USER_ID = None

# SSE Server URLs (from config)
SSE_SERVERS = {
    "google_sheets": "http://127.0.0.1:8100",
    "gmail": "http://127.0.0.1:8101",
    "telegram": "http://127.0.0.1:8102"
}


async def check_sse_server_single(server_name: str, url: str) -> dict:
    """Check if a single SSE server is running."""
    # Use a very short read timeout - SSE streams continuously, so we'll timeout reading
    # But if we can connect and get headers, the server is running
    timeout = httpx.Timeout(connect=2.0, read=1.0, write=1.0, pool=2.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Try a regular GET request - will timeout reading the stream, but that's OK
            response = await client.get(f"{url}/sse")
            return {
                "status": "running" if response.status_code == 200 else "error",
                "url": url,
                "http_status": response.status_code
            }
    except httpx.ReadTimeout:
        # Read timeout means connection was established and server started responding
        # This is expected for SSE endpoints that stream continuously
        return {
            "status": "running",
            "url": url,
            "note": "Server responding (read timeout is normal for SSE streams)"
        }
    except httpx.ConnectError:
        return {
            "status": "not_running",
            "url": url,
            "error": "Connection refused - server not running"
        }
    except httpx.ConnectTimeout:
        return {
            "status": "not_running",
            "url": url,
            "error": "Connection timeout - server not responding"
        }
    except Exception as e:
        error_str = str(e)
        error_type = type(e).__name__
        # If it's any kind of timeout after connection, server is likely running
        if "Timeout" in error_type or "timeout" in error_str.lower():
            return {
                "status": "running",
                "url": url,
                "note": f"Server responding ({error_type})"
            }
        return {
            "status": "error",
            "url": url,
            "error": error_str
        }


async def check_sse_servers() -> dict:
    """Check if SSE servers are running and accessible."""
    results = {}
    # Check all servers concurrently
    tasks = [
        check_sse_server_single(name, url)
        for name, url in SSE_SERVERS.items()
    ]
    server_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for (server_name, url), result in zip(SSE_SERVERS.items(), server_results):
        if isinstance(result, Exception):
            results[server_name] = {
                "status": "error",
                "url": url,
                "error": str(result)
            }
        else:
            results[server_name] = result
    
    return results


def log(stage: str, msg: str):
    """Simple timestamped logger."""
    now = datetime.now().strftime("%H:%M:%S")
    logger.info(f"[{now}] [{stage}] {msg}")


# Get bot info to filter out bot's own messages (after log function is defined)
def initialize_bot_info():
    """Initialize bot user ID to filter out bot's own messages."""
    global BOT_USER_ID
    try:
        bot_info_response = requests.get(f"{TELEGRAM_API_URL}/getMe", timeout=5)
        if bot_info_response.status_code == 200:
            BOT_USER_ID = bot_info_response.json().get("result", {}).get("id")
            log("startup", f"Bot user ID: {BOT_USER_ID}")
        else:
            BOT_USER_ID = None
            log("warning", "Could not get bot info, won't filter bot messages")
    except Exception as e:
        BOT_USER_ID = None
        log("warning", f"Could not get bot info: {e}, won't filter bot messages")


# Initialize bot info on startup
initialize_bot_info()


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
        # Check SSE servers first
        log("agent", "Checking SSE server availability...")
        sse_status = await check_sse_servers()
        not_running = [name for name, status in sse_status.items() if status["status"] != "running"]
        
        if not_running:
            error_msg = f"⚠️ Some SSE servers are not running: {', '.join(not_running)}. Please start them with: python start_sse_servers.py"
            log("error", error_msg)
            send_telegram_message(chat_id, error_msg)
            return error_msg
        
        # Send "thinking" message
        send_telegram_message(chat_id, "🤔 Processing your query...")
        
        log("agent", f"Processing query from chat {chat_id}: {query}")
        
        # Load MCP server configs from profiles.yaml
        with open("config/profiles.yaml", "r") as f:
            profile = yaml.safe_load(f)
            mcp_servers = profile.get("mcp_servers", [])
        
        log("agent", f"Loaded {len(mcp_servers)} MCP server configs")
        
        # Initialize MultiMCP
        log("agent", "Initializing MultiMCP...")
        multi_mcp = MultiMCP(server_configs=mcp_servers)
        try:
            await multi_mcp.initialize()
            log("agent", "MultiMCP initialization completed")
        except Exception as e:
            import traceback
            log("error", f"MultiMCP initialization failed: {e}")
            log("error", f"Traceback: {traceback.format_exc()}")
            return f"Failed to initialize MCP servers: {str(e)}. Check server logs for details."
        
        tools = multi_mcp.get_all_tools()
        tool_names = [t.get('name', str(t)) if isinstance(t, dict) else getattr(t, 'name', str(t)) for t in tools[:10]]
        log("agent", f"Initialized MultiMCP with {len(tools)} tools: {tool_names}")
        
        # Verify critical tools are available
        tool_names_full = [t.get('name', str(t)) if isinstance(t, dict) else getattr(t, 'name', str(t)) for t in tools]
        critical_tools = ['create_google_sheet', 'send_sheet_link', 'search', 'fetch_content']
        missing_tools = [t for t in critical_tools if t not in tool_names_full]
        if missing_tools:
            log("warning", f"Missing critical tools: {missing_tools}")
            log("warning", f"Available tools: {tool_names_full}")
            return f"Error: Critical tools not available: {', '.join(missing_tools)}. Make sure SSE servers are running and initialized correctly."
        
        # Run agent loop
        agent = AgentLoop(
            user_input=query,
            dispatcher=multi_mcp
        )
        
        try:
            log("agent", "Starting agent loop...")
            final_response = await agent.run()
            # Extract final answer from FINAL_ANSWER: prefix
            answer = final_response.replace("FINAL_ANSWER:", "").strip().strip("[]")
            log("agent", f"Agent completed. Final answer length: {len(answer)} chars")
            log("agent", f"Final answer preview: {answer[:200]}...")
            return answer
        
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            log("error", f"Agent failed: {e}")
            log("error", f"Traceback: {error_trace}")
            return f"Sorry, I encountered an error while processing your query: {str(e)}"
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        log("error", f"Failed to process query: {e}")
        log("error", f"Traceback: {error_trace}")
        return f"Sorry, I encountered an error: {str(e)}"


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "Telegram Agent Webhook"}


@app.get("/health")
async def health():
    """Detailed health check."""
    sse_servers_status = await check_sse_servers()
    all_running = all(s["status"] == "running" for s in sse_servers_status.values())
    
    return {
        "status": "healthy" if all_running else "degraded",
        "service": "Telegram Agent Webhook",
        "telegram_configured": bool(config.TELEGRAM_BOT_TOKEN),
        "gmail_configured": bool(config.SENDER_EMAIL and config.RECEIVER_EMAIL),
        "google_sheets_configured": os.path.exists(config.GOOGLE_CREDENTIALS_PATH),
        "sse_servers": sse_servers_status,
        "all_servers_running": all_running
    }


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram webhook updates."""
    # Return 200 immediately to acknowledge receipt (prevents Telegram retries)
    # Then process asynchronously
    
    try:
        data = await request.json()
        update_id = data.get("update_id")
        
        # Check if we've already processed this update
        if update_id in processed_updates:
            log("webhook", f"Duplicate update {update_id}, ignoring")
            return Response(status_code=200)
        
        # Add to processed set
        processed_updates.add(update_id)
        
        # Clean up old update IDs to prevent memory leak
        if len(processed_updates) > MAX_PROCESSED_UPDATES:
            # Remove oldest 100 entries (simple cleanup)
            oldest = sorted(processed_updates)[:100]
            processed_updates.difference_update(oldest)
        
        # Log the update (but don't block on it)
        log("webhook", f"Received update {update_id}")
        
        # Process asynchronously in background
        asyncio.create_task(process_webhook_update(data))
        
        # Return 200 immediately to acknowledge receipt
        return Response(status_code=200)
    
    except Exception as e:
        log("error", f"Webhook error: {e}")
        # Still return 200 to prevent Telegram from retrying
        return Response(status_code=200)


async def process_webhook_update(data: dict):
    """Process a webhook update asynchronously."""
    try:
        # Extract message data
        if "message" not in data:
            return  # Not a message, ignore
        
        message = data["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        message_id = message["message_id"]
        from_user = message.get("from", {})
        user_id = from_user.get("id")
        
        # Filter out bot's own messages (prevent infinite loop)
        if BOT_USER_ID and user_id == BOT_USER_ID:
            log("webhook", f"Ignoring message from bot itself (user_id: {user_id})")
            return
        
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
            return
        
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
            return
        
        # Ignore empty messages
        if not text or len(text.strip()) == 0:
            return
        
        # Process the query
        try:
            log("webhook", f"Processing query from chat {chat_id} (user {user_id}): {text[:100]}")
            
            # Run agent
            answer = await process_query_with_agent(text, str(chat_id))
            
            log("webhook", f"Received answer from agent, length: {len(answer) if answer else 0}")
            
            # Send the result
            if answer:
                # Format answer nicely for Telegram
                message_text = f"✅ <b>Result:</b>\n\n{answer}"
                # Telegram has a 4096 character limit, truncate if needed
                if len(message_text) > 4000:
                    message_text = message_text[:4000] + "\n\n... (truncated)"
                send_telegram_message(str(chat_id), message_text)
                log("webhook", "Successfully sent result to Telegram")
            else:
                log("webhook", "Agent returned empty answer")
                send_telegram_message(str(chat_id), "❌ Sorry, I couldn't process your query.")
        
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            log("error", f"Error processing query: {e}")
            log("error", f"Traceback: {error_trace}")
            try:
                send_telegram_message(str(chat_id), f"❌ Sorry, an error occurred: {str(e)}")
            except:
                log("error", "Failed to send error message to user")
    
    except Exception as e:
        import traceback
        log("error", f"Error in process_webhook_update: {e}")
        log("error", f"Traceback: {traceback.format_exc()}")


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

