# mcp_server_4_googlesheets.py - Google Sheets MCP Server (SSE Transport)

import sys
import os
import json
from datetime import datetime
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from typing import List, Dict, Any
import gspread
from google.oauth2.service_account import Credentials

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

# Create FastMCP instance (settings can be updated later)
mcp = FastMCP("google_sheets")


# Pydantic models for tool I/O
class SheetDataInput(BaseModel):
    title: str
    data: List[List[str]]  # 2D array of strings
    column_headers: List[str] = None  # Optional headers


class SheetDataOutput(BaseModel):
    sheet_id: str
    sheet_url: str
    worksheet_name: str


class ReadSheetInput(BaseModel):
    spreadsheet_id: str
    worksheet_name: str = None  # If None, reads first worksheet
    range_name: str = None  # If None, reads entire sheet


class ReadSheetOutput(BaseModel):
    data: List[List[str]]
    headers: List[str] = None


# Cache for Google Sheets client to avoid re-authentication on every call
_sheets_client_cache = None

# Initialize Google Sheets client
def get_sheets_client():
    """Get authenticated Google Sheets client.
    
    Tries OAuth2 user credentials first (so sheets are created in user's Drive),
    falls back to service account if OAuth2 is not available.
    
    Uses caching to avoid re-authentication on every call.
    """
    global _sheets_client_cache
    
    # Return cached client if available and still valid
    if _sheets_client_cache is not None:
        try:
            # Try a simple operation to verify the client is still valid
            # Just check if we can access the client object
            if hasattr(_sheets_client_cache, 'list_spreadsheet_files'):
                return _sheets_client_cache
        except Exception:
            # Client is invalid, reset cache
            _sheets_client_cache = None
            print("[INFO] Cached client invalid, re-authenticating...")
    
    try:
        # Try OAuth2 flow first (creates sheets in user's Drive, uses user's quota)
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        import pickle
        
        creds = None
        token_file = 'credentials/sheets_token.pickle'
        
        print("[INFO] Getting Google Sheets client...")
        
        # Check if token exists
        if os.path.exists(token_file):
            try:
                with open(token_file, 'rb') as token:
                    creds = pickle.load(token)
                print("[INFO] Loaded existing token")
            except Exception as e:
                print(f"[WARNING] Could not load token file: {e}")
                creds = None
        
        # If no valid credentials, check for OAuth client secrets
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    print("[INFO] Token expired, refreshing...")
                    creds.refresh(Request())
                    print("[INFO] Token refreshed successfully")
                except Exception as refresh_error:
                    print(f"[WARNING] Could not refresh token: {refresh_error}")
                    print("[INFO] Will need to re-authorize")
                    creds = None
            
            if not creds or not creds.valid:
                # Try to find OAuth credentials
                oauth_creds_path = os.path.join(os.path.dirname(config.GOOGLE_CREDENTIALS_PATH), 'gmail_oauth_credentials.json')
                if not os.path.exists(oauth_creds_path):
                    # Try alternative path
                    oauth_creds_path = os.path.join(os.path.dirname(config.GOOGLE_CREDENTIALS_PATH), 'oauth_credentials.json')
                
                if os.path.exists(oauth_creds_path):
                    print("[ERROR] OAuth token expired and refresh failed. Please run setup_sheets_oauth.py to re-authorize.")
                    print("[INFO] Falling back to service account for now...")
                    # Don't try OAuth flow in server context (it's blocking)
                    raise FileNotFoundError("OAuth token expired, re-authorization needed")
                else:
                    # Fall back to service account
                    print("[INFO] No OAuth credentials found, using service account (sheets will use service account quota)")
                    raise FileNotFoundError("OAuth credentials not found")
            
            # Save credentials for next time
            if creds:
                try:
                    os.makedirs(os.path.dirname(token_file), exist_ok=True)
                    with open(token_file, 'wb') as token:
                        pickle.dump(creds, token)
                    print("[INFO] Token saved successfully")
                except Exception as save_error:
                    print(f"[WARNING] Could not save token: {save_error}")
        
        # Authorize with gspread
        try:
            client = gspread.authorize(creds)
            print("[INFO] Using OAuth2 user credentials (sheets will be created in your Drive)")
            # Cache the client
            _sheets_client_cache = client
            return client
        except Exception as auth_error:
            print(f"[ERROR] Failed to authorize with OAuth2 credentials: {auth_error}")
            # If authorization fails, try to re-authenticate
            if os.path.exists(token_file):
                print("[INFO] Removing invalid token file, will re-authenticate on next attempt")
                try:
                    os.remove(token_file)
                except:
                    pass
            raise
        
    except (FileNotFoundError, ImportError) as e:
        # Fallback to service account
        print(f"[INFO] OAuth2 not available ({e}), using service account")
        try:
            creds = Credentials.from_service_account_file(
                config.GOOGLE_CREDENTIALS_PATH,
                scopes=config.SHEETS_SCOPES
            )
            client = gspread.authorize(creds)
            print("[WARNING] Using service account - sheets will use service account's Drive quota")
            # Cache the client
            _sheets_client_cache = client
            return client
        except Exception as e2:
            raise Exception(f"Failed to initialize Google Sheets client: {e2}")
    except Exception as e:
        raise Exception(f"Failed to initialize Google Sheets client: {e}")


@mcp.tool()
def create_google_sheet(input: SheetDataInput) -> SheetDataOutput:
    """
    Create a new Google Sheet with the provided data.
    
    Args:
        input: SheetDataInput with title, data, and optional column_headers
        
    Returns:
        SheetDataOutput with sheet_id, sheet_url, and worksheet_name
    """
    print(f"[INFO] CALLED: create_google_sheet with title: {input.title}")
    print(f"[INFO] Data rows: {len(input.data) if input.data else 0}")
    
    try:
        print("[INFO] Getting Google Sheets client...")
        client = get_sheets_client()
        print("[INFO] Client obtained, creating spreadsheet...")
        
        # Create a new spreadsheet
        spreadsheet = client.create(input.title)
        print(f"[INFO] Spreadsheet created: {spreadsheet.id}")
        
        # Get the first worksheet
        worksheet = spreadsheet.sheet1
        
        # Add column headers if provided
        if input.column_headers:
            print(f"[INFO] Adding column headers: {input.column_headers}")
            worksheet.append_row(input.column_headers)
        
        # Add data rows
        if input.data:
            print(f"[INFO] Adding {len(input.data)} data rows...")
            worksheet.append_rows(input.data)
            print("[INFO] Data rows added")
        
        # If using service account, share with user's email
        # (If using OAuth2, the sheet is already in the user's Drive)
        try:
            user_email = getattr(config, 'RECEIVER_EMAIL', None) or getattr(config, 'SENDER_EMAIL', None)
            if user_email:
                # Share with user email as editor
                print(f"[INFO] Sharing sheet with {user_email}...")
                spreadsheet.share(user_email, perm_type='user', role='writer')
                print(f"[INFO] Shared sheet with {user_email}")
            # Also make it publicly readable for easy access
            spreadsheet.share("", perm_type="anyone", role="reader")
            print("[INFO] Made sheet publicly readable")
        except Exception as share_error:
            print(f"[WARNING] Could not share sheet: {share_error}")
            # Continue even if sharing fails
        
        print(f"[SUCCESS] Created Google Sheet: {spreadsheet.url}")
        
        return SheetDataOutput(
            sheet_id=spreadsheet.id,
            sheet_url=spreadsheet.url,
            worksheet_name=worksheet.title
        )
    
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Error creating Google Sheet: {error_msg}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        # Return a more descriptive error
        raise Exception(f"Failed to create Google Sheet: {error_msg}")


@mcp.tool()
def read_google_sheet(input: ReadSheetInput) -> ReadSheetOutput:
    """
    Read data from an existing Google Sheet.
    
    Args:
        input: ReadSheetInput with spreadsheet_id, optional worksheet_name and range_name
        
    Returns:
        ReadSheetOutput with data and headers
    """
    print(f"CALLED: read_google_sheet from spreadsheet: {input.spreadsheet_id}")
    
    try:
        client = get_sheets_client()
        
        # Open the spreadsheet
        spreadsheet = client.open_by_key(input.spreadsheet_id)
        
        # Get the worksheet
        if input.worksheet_name:
            worksheet = spreadsheet.worksheet(input.worksheet_name)
        else:
            worksheet = spreadsheet.sheet1
        
        # Read data
        if input.range_name:
            values = worksheet.get(input.range_name)
        else:
            values = worksheet.get_all_values()
        
        # Separate headers if data exists
        headers = None
        data = []
        
        if values:
            if input.range_name is None:
                # First row is typically headers
                headers = values[0] if len(values) > 0 else []
                data = values[1:] if len(values) > 1 else []
            else:
                # Return all data if range is specified
                data = values
        
        return ReadSheetOutput(
            data=data,
            headers=headers
        )
    
    except Exception as e:
        print(f"[ERROR] Error reading Google Sheet: {e}")
        raise Exception(f"Failed to read Google Sheet: {e}")


@mcp.tool()
def append_to_sheet(spreadsheet_id: str, data: List[List[str]]) -> str:
    """
    Append rows to an existing Google Sheet.
    
    Args:
        spreadsheet_id: The ID of the Google Sheet
        data: 2D array of strings to append
        
    Returns:
        Success message with row count
    """
    print(f"CALLED: append_to_sheet for spreadsheet: {spreadsheet_id}")
    
    try:
        client = get_sheets_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.sheet1
        
        worksheet.append_rows(data)
        
        return f"Successfully appended {len(data)} rows to the sheet."
    
    except Exception as e:
        print(f"[ERROR] Error appending to Google Sheet: {e}")
        raise Exception(f"Failed to append to Google Sheet: {e}")


@mcp.resource("sheet://{spreadsheet_id}")
def get_sheet_info(spreadsheet_id: str) -> str:
    """Get information about a Google Sheet."""
    try:
        client = get_sheets_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        info = {
            "title": spreadsheet.title,
            "url": spreadsheet.url,
            "id": spreadsheet.id
        }
        return json.dumps(info, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    print("Starting Google Sheets MCP Server (SSE)...")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Development mode
    else:
        # Run with SSE transport
        port = int(os.getenv("SSE_PORT", config.SSE_PORT))
        # Update settings for host and port
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = port
        print(f"Server will run on http://127.0.0.1:{port}")
        mcp.run(transport="sse")
        print(f"\nServer running on http://127.0.0.1:{port}")
        print("Shutting down...")

