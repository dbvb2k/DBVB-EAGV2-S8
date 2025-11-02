# Quick Start Guide

## Prerequisites Checklist

- [ ] Python 3.11+ installed
- [ ] Telegram bot token from @BotFather
- [ ] Google Cloud project with APIs enabled
- [ ] Ollama running locally (optional)

## Setup Steps

### 1. Install Dependencies

```bash
uv sync
# or
pip install -r requirements.txt
```

### 2. Configure Application

```bash
# Copy example config
cp config.py.example config.py

# Edit config.py with your credentials
# - Telegram bot token
# - Gmail sender/receiver
# - Google credentials path
```

### 3. Set Up Google Credentials

Create `credentials/` directory:
```bash
mkdir credentials
```

Download and save:
- Service account JSON → `credentials/google_credentials.json`
- OAuth2 JSON → `credentials/gmail_oauth_credentials.json`

### 4. Authenticate Gmail (One Time)

```bash
python credentials_setup.py
```

Follow the OAuth flow in your browser.

### 5. Run the Application

**Option A: Telegram Webhook (Production)**
```bash
python telegram_webhook.py
```

**Option B: Local Agent**
```bash
python agent.py
```

## Test the Workflow

1. Open Telegram, find your bot
2. Send: `/start`
3. Send: `"Find the Current Point Standings of F1 Racers"`
4. Check your email for the Google Sheet link

## Troubleshooting

**"Config not found"** → Copy `config.py.example` to `config.py`

**"Credentials not found"** → Download JSON files to `credentials/`

**"Gmail auth error"** → Run `python credentials_setup.py`

**"Telegram not responding"** → Verify bot token in `config.py`

## Need More Details?

See `SETUP.md` for comprehensive instructions.

