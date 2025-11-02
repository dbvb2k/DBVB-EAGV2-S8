# credentials_setup.py - Setup Gmail OAuth2 credentials

"""
This script helps set up Gmail OAuth2 credentials for the first time.
Run this once to authenticate with Gmail.
"""

import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Gmail scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Check for OAuth credentials file
oauth_creds_path = 'credentials/gmail_oauth_credentials.json'
token_file = 'credentials/gmail_token.pickle'

if not os.path.exists(oauth_creds_path):
    print("❌ Error: OAuth credentials file not found!")
    print(f"Please download your OAuth2 client ID JSON from Google Cloud Console")
    print(f"and save it as: {oauth_creds_path}")
    print("\nTo get OAuth credentials:")
    print("1. Go to https://console.cloud.google.com/")
    print("2. APIs & Services → Credentials")
    print("3. Create Credentials → OAuth client ID")
    print("4. Application type: Desktop app")
    print("5. Download JSON and save as gmail_oauth_credentials.json")
    exit(1)

print("🔐 Starting Gmail OAuth2 flow...")
print("A browser window will open. Please sign in to your Google account.")
print()

creds = None

# Check if token exists
if os.path.exists(token_file):
    with open(token_file, 'rb') as token:
        creds = pickle.load(token)

# If no valid credentials, run OAuth flow
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        print("Refreshing expired token...")
        creds.refresh(Request())
    else:
        print("Starting new OAuth flow...")
        flow = InstalledAppFlow.from_client_secrets_file(oauth_creds_path, SCOPES)
        creds = flow.run_local_server(port=0)
    
    # Save credentials for next time
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    with open(token_file, 'wb') as token:
        pickle.dump(creds, token)
    
    print("✅ OAuth credentials saved successfully!")
    print(f"Token saved to: {token_file}")
else:
    print("✅ Valid credentials already exist!")
    print(f"Token file: {token_file}")

print("\nYou can now use the Gmail MCP server.")

