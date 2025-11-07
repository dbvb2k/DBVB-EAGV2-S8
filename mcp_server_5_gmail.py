# mcp_server_5_gmail.py - Gmail MCP Server (SSE Transport)

import sys
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from typing import Optional
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import json

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

mcp = FastMCP("gmail")


# Pydantic models for tool I/O
class SendEmailInput(BaseModel):
    to: str
    subject: str
    body: str
    is_html: bool = False  # If True, body is HTML; if False, plain text


class SendEmailOutput(BaseModel):
    message_id: str
    status: str


# Initialize Gmail client
def get_gmail_client():
    """Get authenticated Gmail client."""
    try:
        # Try OAuth2 flow first
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        import pickle
        
        creds = None
        token_file = 'credentials/gmail_token.pickle'
        
        # Check if token exists
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
        
        # If no valid credentials, check for OAuth client secrets
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                oauth_creds_path = os.path.join(os.path.dirname(config.GOOGLE_CREDENTIALS_PATH), 'gmail_oauth_credentials.json')
                if os.path.exists(oauth_creds_path):
                    flow = InstalledAppFlow.from_client_secrets_file(oauth_creds_path, config.GMAIL_SCOPES)
                    creds = flow.run_local_server(port=0)
                else:
                    raise Exception("No OAuth credentials found. Please set up OAuth2 flow.")
            
            # Save credentials for next time
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        service = build('gmail', 'v1', credentials=creds)
        return service
    
    except Exception as e:
        print(f"OAuth flow failed, trying service account: {e}")
        # Fallback to service account
        try:
            creds = Credentials.from_service_account_file(
                config.GOOGLE_CREDENTIALS_PATH,
                scopes=config.GMAIL_SCOPES
            )
            service = build('gmail', 'v1', credentials=creds)
            return service
        except Exception as e2:
            raise Exception(f"Failed to initialize Gmail client: {e2}")


def create_message(sender: str, to: str, subject: str, body_text: str, is_html: bool = False) -> dict:
    """Create a message for an email."""
    message = MIMEMultipart('alternative')
    message['From'] = sender
    message['To'] = to
    message['Subject'] = subject
    
    if is_html:
        message.attach(MIMEText(body_text, 'html'))
    else:
        message.attach(MIMEText(body_text, 'plain'))
    
    # Encode message
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    return {'raw': raw_message}


@mcp.tool()
def send_email(input: SendEmailInput) -> SendEmailOutput:
    """
    Send an email via Gmail.
    
    Args:
        input: SendEmailInput with to, subject, body, and is_html flag
        
    Returns:
        SendEmailOutput with message_id and status
    """
    print(f"CALLED: send_email to {input.to}")
    
    try:
        # Get sender from config
        sender = config.SENDER_EMAIL
        
        # Create message
        message = create_message(
            sender=sender,
            to=input.to,
            subject=input.subject,
            body_text=input.body,
            is_html=input.is_html
        )
        
        # For service accounts, we need to use domain-wide delegation
        # For testing, we can use OAuth2 flow instead
        # This is a simplified version - you may need to adjust based on your setup
        
        # Alternative: Use OAuth2 for user-based authentication
        # This requires user consent and OAuth2 credentials
        
        # For now, we'll use a simple implementation
        # You'll need to set up proper OAuth2 credentials for this to work
        
        # Get Gmail service (this may need adjustments based on your auth method)
        try:
            service = get_gmail_client()
            sent_message = service.users().messages().send(
                userId='me',
                body=message
            ).execute()
            
            print(f"[SUCCESS] Email sent. Message ID: {sent_message['id']}")
            
            return SendEmailOutput(
                message_id=sent_message['id'],
                status="sent"
            )
        except Exception as auth_error:
            # Fallback: return info that email would be sent
            print(f"⚠️ Gmail API auth error: {auth_error}")
            print("Please set up OAuth2 credentials for user-based authentication")
            
            # Return simulated response for development
            return SendEmailOutput(
                message_id="simulated_" + str(hash(f"{input.to}{input.subject}")),
                status="simulated (Gmail API not configured)"
            )
    
    except Exception as e:
        print(f"[ERROR] Error sending email: {e}")
        raise Exception(f"Failed to send email: {e}")


@mcp.tool()
def send_sheet_link(to: str, sheet_url: str, sheet_title: str) -> SendEmailOutput:
    """
    Convenience tool to send a Google Sheet link via email.
    
    Args:
        to: Recipient email address
        sheet_url: URL of the Google Sheet
        sheet_title: Title of the sheet
        
    Returns:
        SendEmailOutput with message_id and status
    """
    print(f"CALLED: send_sheet_link to {to}")
    
    subject = f"Your Google Sheet: {sheet_title}"
    
    body_html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
            <h2>Your Google Sheet is Ready</h2>
            <p>Click the link below to view your sheet:</p>
            <p><a href="{sheet_url}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Open {sheet_title}</a></p>
            <p style="color: #666; font-size: 12px;">Or copy this link: <a href="{sheet_url}">{sheet_url}</a></p>
            <hr style="border: 1px solid #eee; margin: 20px 0;">
            <p style="color: #999; font-size: 11px;">This is an automated message from your Agentic AI Assistant.</p>
        </body>
    </html>
    """
    
    body_text = f"""
Your Google Sheet is Ready

Title: {sheet_title}
Link: {sheet_url}

Click the link above or copy it to your browser to view the sheet.

---
This is an automated message from your Agentic AI Assistant.
"""
    
    # Try HTML first, fallback to plain text
    try:
        result = send_email(SendEmailInput(
            to=to,
            subject=subject,
            body=body_html,
            is_html=True
        ))
        print(f"[SUCCESS] send_sheet_link completed (HTML)")
        return result
    except Exception as e1:
        print(f"[WARNING] HTML email failed, trying plain text: {e1}")
        try:
            result = send_email(SendEmailInput(
                to=to,
                subject=subject,
                body=body_text,
                is_html=False
            ))
            print(f"[SUCCESS] send_sheet_link completed (plain text)")
            return result
        except Exception as e2:
            print(f"[ERROR] Both HTML and plain text email failed: {e2}")
            # Don't raise - return error info instead so agent can retry
            return SendEmailOutput(
                message_id="failed_" + str(hash(f"{to}{sheet_url}")),
                status=f"failed: {str(e2)}"
            )


@mcp.resource("email://{email_id}")
def get_email_info(email_id: str) -> str:
    """Get information about a sent email."""
    try:
        service = get_gmail_client()
        message = service.users().messages().get(
            userId='me',
            id=email_id
        ).execute()
        
        info = {
            "id": message['id'],
            "threadId": message.get('threadId'),
            "labelIds": message.get('labelIds', [])
        }
        return json.dumps(info, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    print("Starting Gmail MCP Server (SSE)...")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Development mode
    else:
        # Run with SSE transport
        port = int(os.getenv("SSE_PORT", config.SSE_PORT)) + 1
        # Update settings for host and port
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = port
        print(f"Server will run on http://127.0.0.1:{port}")
        mcp.run(transport="sse")
        print(f"\nServer running on http://127.0.0.1:{port}")
        print("Shutting down...")

