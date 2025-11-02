# mcp_server_4_googlesheets.py - Google Sheets MCP Server

import sys
import os
import json
from datetime import datetime
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from typing import List, Dict, Any
import gspread
from google.oauth2.service_account import Credentials

# Import config
try:
    import config
except ImportError:
    print("Warning: config.py not found. Please create it with required settings.")
    sys.exit(1)

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


# Initialize Google Sheets client
def get_sheets_client():
    """Get authenticated Google Sheets client."""
    try:
        creds = Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_PATH,
            scopes=config.SHEETS_SCOPES
        )
        client = gspread.authorize(creds)
        return client
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
    print(f"CALLED: create_google_sheet with title: {input.title}")
    
    try:
        client = get_sheets_client()
        
        # Create a new spreadsheet
        spreadsheet = client.create(input.title)
        
        # Get the first worksheet
        worksheet = spreadsheet.sheet1
        
        # Add column headers if provided
        if input.column_headers:
            worksheet.append_row(input.column_headers)
        
        # Add data rows
        if input.data:
            worksheet.append_rows(input.data)
        
        # Make the sheet publicly readable (optional, for sharing)
        spreadsheet.share("", perm_type="anyone", role="reader")
        
        print(f"✅ Created Google Sheet: {spreadsheet.url}")
        
        return SheetDataOutput(
            sheet_id=spreadsheet.id,
            sheet_url=spreadsheet.url,
            worksheet_name=worksheet.title
        )
    
    except Exception as e:
        print(f"❌ Error creating Google Sheet: {e}")
        raise Exception(f"Failed to create Google Sheet: {e}")


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
        print(f"❌ Error reading Google Sheet: {e}")
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
        print(f"❌ Error appending to Google Sheet: {e}")
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
    print("Starting Google Sheets MCP Server...")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Development mode
    else:
        # Run with stdio transport
        mcp.run(transport="stdio")
        print("\nShutting down...")

