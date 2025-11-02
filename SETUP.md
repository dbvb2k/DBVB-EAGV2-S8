# Setup Guide for Agentic AI Application

This guide will help you set up the complete Agentic AI application with Telegram, Gmail, and Google Sheets integration.

## Prerequisites

- Python 3.11 or higher
- Telegram Bot Token (from @BotFather)
- Google Cloud Project with APIs enabled
- Google Service Account credentials

## Installation Steps

### 1. Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

### 2. Set Up Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the following APIs:
   - Google Sheets API
   - Gmail API
   - Google Drive API

4. Create a Service Account:
   - Go to "IAM & Admin" → "Service Accounts"
   - Click "Create Service Account"
   - Give it a name (e.g., "agentic-ai-bot")
   - Grant it roles: "Editor" or "Owner"
   - Create a JSON key and download it

5. Save the JSON key file as `credentials/google_credentials.json`

### 3. Set Up Gmail (User-based Authentication)

For Gmail to work with user accounts, you need OAuth2 credentials:

1. In Google Cloud Console, go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: "Desktop app"
4. Download the credentials JSON file
5. Save it as `credentials/gmail_oauth_credentials.json`

### 4. Configure Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Start a conversation and run `/newbot`
3. Follow the instructions to create a bot
4. Copy the bot token

### 5. Configure the Application

Edit `config.py` with your actual values:

```python
# Gmail Configuration
SENDER_EMAIL = "your-email@gmail.com"
RECEIVER_EMAIL = "receiver@gmail.com"

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = "YOUR_ACTUAL_BOT_TOKEN"

# Google API Configuration
GOOGLE_CREDENTIALS_PATH = "credentials/google_credentials.json"
```

### 6. Set Up Environment

Create a `credentials` directory:

```bash
mkdir credentials
```

Place your credential files in it:
- `credentials/google_credentials.json` - Service account credentials
- `credentials/gmail_oauth_credentials.json` - OAuth2 credentials (for Gmail)

### 7. Additional Configuration for Google Sheets

When using Google Sheets with a service account:

1. Create a new Google Sheet manually
2. Share it with the service account email (found in `google_credentials.json` as `client_email`)
3. Give it "Editor" permissions

Alternatively, the bot can create sheets programmatically if the service account has proper permissions.

## Running the Application

### Option 1: Webhook Mode (Production)

Start the Telegram webhook server:

```bash
python telegram_webhook.py
```

The server will run on port 8001 (or configured port).

### Option 2: Local Development

For development, you can run individual MCP servers in dev mode:

```bash
# Start Google Sheets server (dev mode)
python mcp_server_4_googlesheets.py dev

# Start Gmail server (dev mode)
python mcp_server_5_gmail.py dev

# Start Telegram server (dev mode)
python mcp_server_6_telegram.py dev
```

Or run the main agent which will handle MCP servers automatically:

```bash
python agent.py
```

## Testing the Workflow

1. Open Telegram and find your bot
2. Send `/start` to initialize
3. Send a query like: "Find the Current Point Standings of F1 Racers"
4. The agent will:
   - Process your query using web search
   - Store results in a Google Sheet
   - Email you the sheet link

## Webhook Setup

To use webhooks for production:

1. Deploy your application to a public server (e.g., Heroku, AWS, GCP)
2. Set the webhook URL:
   ```bash
   curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://yourdomain.com/webhook
   ```

3. Or use the built-in endpoint:
   ```bash
   curl http://localhost:8001/set_webhook?webhook_url=https://yourdomain.com/webhook
   ```

## Troubleshooting

### Gmail API Errors

If you see Gmail API errors, you may need to:
1. Enable Gmail API in Google Cloud Console
2. Configure OAuth consent screen
3. Add test users if the app is not verified
4. Use the OAuth2 flow for user-based authentication

### Google Sheets Permissions

Ensure your service account has proper permissions:
- Check the `client_email` in `google_credentials.json`
- Share any existing sheets with that email
- Or grant the service account broader permissions

### Telegram Bot Not Responding

1. Verify your bot token is correct
2. Check that the webhook is set correctly
3. Look at server logs for errors
4. Ensure the bot is not blocked by Telegram

## Architecture

The application consists of:

1. **Agent Core** (`core/`):
   - `loop.py` - Main agent loop
   - `session.py` - MCP session management
   - `context.py` - Agent context
   - `strategy.py` - Decision making

2. **MCP Servers**:
   - `mcp_server_1.py` - Math and calculator tools
   - `mcp_server_2.py` - Document processing
   - `mcp_server_3.py` - Web search (DuckDuckGo)
   - `mcp_server_4_googlesheets.py` - Google Sheets integration
   - `mcp_server_5_gmail.py` - Gmail integration
   - `mcp_server_6_telegram.py` - Telegram bot integration

3. **Webhook Handler**:
   - `telegram_webhook.py` - FastAPI webhook server

4. **Configuration**:
   - `config.py` - Application configuration
   - `config/profiles.yaml` - Agent profiles and MCP server configs

## Security Notes

- Never commit your `config.py` or credential files to version control
- Use environment variables for sensitive data in production
- Keep your bot token secret
- Regularly rotate API keys and credentials
- Use OAuth2 for Gmail instead of service accounts where possible

## Support

If you encounter issues:
1. Check the logs for error messages
2. Verify all credentials are correct
3. Ensure all APIs are enabled
4. Test each component individually

