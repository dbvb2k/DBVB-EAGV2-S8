# OAuth2 Setup for Google Sheets

This guide explains how to set up OAuth2 authentication for Google Sheets so that sheets are created in your personal Google Drive (using your storage quota) instead of the service account's Drive.

## Why OAuth2?

Service accounts have their own Drive storage quota (typically 15 GB shared). When using a service account, sheets are created in the service account's Drive, which can quickly fill up. OAuth2 allows the application to create sheets in **your** Google Drive, using **your** storage quota.

## Prerequisites

1. ✅ OAuth2 credentials file: `credentials/gmail_oauth_credentials.json`
   - If you don't have this, see the main SETUP.md for instructions on creating OAuth credentials

## First-Time Authorization

When you first start the Google Sheets server with OAuth2, you'll need to authorize the application:

1. **Start the SSE servers:**
   ```bash
   python start_sse_servers.py
   ```

2. **Watch for the authorization prompt:**
   - The Google Sheets server will detect that no authorization token exists
   - It will automatically open a browser window
   - If the browser doesn't open automatically, check the server output for a URL

3. **Authorize the application:**
   - Sign in with your Google account (the one you want to use for creating sheets)
   - Review the permissions requested:
     - Google Sheets API (to create and edit sheets)
     - Google Drive API (to create files in your Drive)
   - Click "Allow" or "Continue"

4. **Authorization complete:**
   - The authorization token will be saved to `credentials/sheets_token.pickle`
   - Future server starts will use this token automatically
   - You won't need to authorize again unless the token expires

## Verification

After authorization, when you create a sheet, you should see:
```
[INFO] Using OAuth2 user credentials (sheets will be created in your Drive)
[SUCCESS] Created Google Sheet: https://docs.google.com/spreadsheets/...
```

The sheet will appear in **your** Google Drive, not the service account's Drive.

## Troubleshooting

### Browser doesn't open automatically
- Check the server output for a URL like `http://localhost:XXXXX`
- Copy and paste this URL into your browser manually
- Complete the authorization flow

### "OAuth credentials not found" error
- Make sure `credentials/gmail_oauth_credentials.json` exists
- Verify the file is valid JSON
- Check that the file path is correct

### Token expired
- Delete `credentials/sheets_token.pickle`
- Restart the server
- The authorization flow will start again

### Still using service account
- Check the server output for messages like:
  - `[INFO] OAuth2 not available, using service account`
  - `[WARNING] Using service account - sheets will use service account's Drive quota`
- If you see these, OAuth2 setup didn't work - check the error messages above

## Fallback Behavior

If OAuth2 is not available or fails, the application will automatically fall back to using the service account. However, this means sheets will use the service account's Drive quota, which may be limited.

