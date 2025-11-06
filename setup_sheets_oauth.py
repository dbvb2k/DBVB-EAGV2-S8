#!/usr/bin/env python3
"""
Helper script to set up OAuth2 authentication for Google Sheets.
Run this script separately to complete the OAuth2 flow before starting the servers.

This script will:
1. Check for OAuth credentials
2. Open a browser for authorization
3. Save the token for use by the Google Sheets server
"""

import os
import sys
import pickle
from pathlib import Path

# Fix encoding issues on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    import config
except ImportError:
    print("Error: config.py not found. Please create it first.")
    sys.exit(1)

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
except ImportError:
    print("Error: google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib")
    sys.exit(1)

def setup_oauth():
    """Set up OAuth2 authentication for Google Sheets."""
    
    token_file = 'credentials/sheets_token.pickle'
    creds = None
    
    # Check if token already exists
    if os.path.exists(token_file):
        try:
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
            
            if creds and creds.valid:
                print("[SUCCESS] Valid OAuth token already exists!")
                print(f"   Token file: {token_file}")
                print("   You can start the servers now.")
                return True
            elif creds and creds.expired and creds.refresh_token:
                print("[INFO] Token expired, attempting to refresh...")
                try:
                    creds.refresh(Request())
                    with open(token_file, 'wb') as token:
                        pickle.dump(creds, token)
                    print("[SUCCESS] Token refreshed successfully!")
                    return True
                except Exception as e:
                    print(f"[ERROR] Could not refresh token: {e}")
                    print("   Will need to re-authenticate...")
        except Exception as e:
            print(f"[WARNING] Could not load existing token: {e}")
            print("   Will create a new token...")
    
    # Find OAuth credentials file
    oauth_creds_path = os.path.join(os.path.dirname(config.GOOGLE_CREDENTIALS_PATH), 'gmail_oauth_credentials.json')
    if not os.path.exists(oauth_creds_path):
        oauth_creds_path = os.path.join(os.path.dirname(config.GOOGLE_CREDENTIALS_PATH), 'oauth_credentials.json')
    
    if not os.path.exists(oauth_creds_path):
        print("[ERROR] OAuth credentials not found!")
        print(f"   Expected location: {oauth_creds_path}")
        print("\n   Please create OAuth credentials:")
        print("   1. Go to Google Cloud Console")
        print("   2. APIs & Services -> Credentials")
        print("   3. Create Credentials -> OAuth client ID")
        print("   4. Application type: Desktop app")
        print("   5. Download and save as: credentials/gmail_oauth_credentials.json")
        return False
    
    print("[INFO] Starting OAuth2 authentication flow...")
    print("   A browser window will open for authorization.")
    print("   Please sign in with your Google account and grant permissions.")
    print()
    
    try:
        # Create the flow
        flow = InstalledAppFlow.from_client_secrets_file(
            oauth_creds_path,
            config.SHEETS_SCOPES
        )
        
        # Run the flow
        creds = flow.run_local_server(port=0)
        
        # Save the credentials
        os.makedirs(os.path.dirname(token_file), exist_ok=True)
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
        
        print()
        print("[SUCCESS] OAuth2 authentication successful!")
        print(f"   Token saved to: {token_file}")
        print("   You can now start the servers.")
        return True
        
    except Exception as e:
        print(f"[ERROR] OAuth2 authentication failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Google Sheets OAuth2 Setup")
    print("=" * 60)
    print()
    
    success = setup_oauth()
    
    if success:
        print()
        print("Next steps:")
        print("1. Start the SSE servers: python start_sse_servers.py")
        print("2. Run the agent: python agent.py")
        sys.exit(0)
    else:
        print()
        print("Setup incomplete. Please fix the errors above and try again.")
        sys.exit(1)

