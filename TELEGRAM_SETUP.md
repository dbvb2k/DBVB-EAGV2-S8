# Telegram Bot Setup and Troubleshooting

## Quick Start

### 1. Start SSE Servers (Required)

The Telegram bot requires SSE servers to be running for Google Sheets, Gmail, and Telegram tools.

**Terminal 1 - Start SSE Servers:**
```bash
python start_sse_servers.py
```

You should see:
```
✅ Google Sheets started (PID: ...)
✅ Gmail started (PID: ...)
✅ Telegram started (PID: ...)
```

### 2. Start Telegram Webhook

**Terminal 2 - Start Webhook:**
```bash
uv run python telegram_webhook.py
```

The webhook will run on port 8001 (default).

### 3. Set Telegram Webhook URL

You need to tell Telegram where to send messages. Use one of these methods:

**Option A: Using ngrok (for local development):**
```bash
ngrok http 8001
```
Then use the ngrok URL:
```bash
curl "http://localhost:8001/set_webhook?webhook_url=https://your-ngrok-url.ngrok.io/webhook"
```

**Option B: Using a public server:**
```bash
curl "http://localhost:8001/set_webhook?webhook_url=https://your-domain.com/webhook"
```

**Option C: Manual Telegram API call:**
```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-domain.com/webhook"}'
```

## Testing

### 1. Check Health

Visit: `http://localhost:8001/health`

You should see:
```json
{
  "status": "healthy",
  "all_servers_running": true,
  "sse_servers": {
    "google_sheets": {"status": "running", ...},
    "gmail": {"status": "running", ...},
    "telegram": {"status": "running", ...}
  }
}
```

### 2. Send a Test Message

In Telegram, send your bot a message:
```
Find the winner in Women's Cricket World Cup in 2025
```

Expected behavior:
1. Bot responds: "🤔 Processing your query..."
2. Agent searches the web
3. Agent fetches content
4. Agent creates a Google Sheet
5. Agent sends email with sheet link
6. Bot responds with final answer

## Troubleshooting

### Issue: "Some SSE servers are not running"

**Solution:**
1. Make sure `start_sse_servers.py` is running
2. Check the terminal output for errors
3. Verify ports 8100, 8101, 8102 are not in use:
   ```bash
   # Windows
   netstat -an | findstr "8100 8101 8102"
   
   # Linux/Mac
   lsof -i :8100 -i :8101 -i :8102
   ```

### Issue: Bot doesn't respond to messages

**Check:**
1. Webhook is set correctly (use `/set_webhook` endpoint)
2. Webhook server is running on port 8001
3. Webhook URL is publicly accessible (use ngrok for local dev)
4. Check webhook logs for incoming requests

### Issue: Agent finds answer but doesn't create sheet/send email

**Possible causes:**
1. **SSE servers not running** - Check with `/health` endpoint
2. **OAuth token expired** - Run `python setup_sheets_oauth.py`
3. **Agent skipping steps** - Check webhook logs for agent execution
4. **Rate limiting** - Check for Gemini API rate limit errors in logs

**Debug:**
1. Check webhook terminal logs for detailed agent execution
2. Check SSE server terminal logs for tool execution
3. Verify agent is following the workflow:
   - Search → Fetch → Create Sheet → Send Email → Final Answer

### Issue: "Failed to create Google Sheet" or "Failed to send email"

**Check:**
1. Google Sheets OAuth token: `credentials/sheets_token.pickle` exists
2. If token expired, run: `python setup_sheets_oauth.py`
3. Gmail credentials in `config.py` are correct
4. Check server logs for specific error messages

### Issue: Timeout errors

**Solution:**
1. SSE client timeout is set to 120 seconds (should be enough)
2. If OAuth authentication is required, it may take longer
3. Check server logs to see if operations are completing
4. Verify network connectivity to Google APIs

## Logs

### Webhook Logs (Terminal 2)
- Agent initialization
- Tool execution
- Final answers
- Errors and tracebacks

### SSE Server Logs (Terminal 1)
- Server startup
- Tool calls (create_google_sheet, send_email, etc.)
- Google API operations
- OAuth authentication

### Key Log Messages to Look For:
- `[agent] Processing query from chat...` - Query received
- `[agent] Initialized MultiMCP with X tools` - Tools loaded
- `[agent] Starting agent loop...` - Agent running
- `[INFO] CALLED: create_google_sheet...` - Sheet creation started
- `[SUCCESS] Created Google Sheet: ...` - Sheet created
- `[agent] Agent completed` - Agent finished

## Verification Checklist

- [ ] SSE servers running (`start_sse_servers.py`)
- [ ] Webhook server running (`telegram_webhook.py`)
- [ ] Webhook URL set correctly
- [ ] Health check shows all servers running (`/health`)
- [ ] OAuth token exists (`credentials/sheets_token.pickle`)
- [ ] Config file has correct credentials (`config.py`)
- [ ] Bot token is valid (`TELEGRAM_BOT_TOKEN`)
- [ ] Test query works end-to-end

## Common Commands

```bash
# Start SSE servers
python start_sse_servers.py

# Start webhook
uv run python telegram_webhook.py

# Check health
curl http://localhost:8001/health

# Set webhook (replace with your URL)
curl "http://localhost:8001/set_webhook?webhook_url=https://your-url.com/webhook"

# Re-authorize Google Sheets
python setup_sheets_oauth.py
```

