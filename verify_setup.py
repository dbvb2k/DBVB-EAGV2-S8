# verify_setup.py - Verify the setup is complete

import os
import sys

def check_file_exists(path: str, description: str) -> bool:
    """Check if a file exists."""
    if os.path.exists(path):
        print(f"✅ {description}: {path}")
        return True
    else:
        print(f"❌ {description}: {path} (NOT FOUND)")
        return False

def check_config_value(config_var: str, expected_placeholder: str = None) -> bool:
    """Check if a config variable is set."""
    try:
        import config
        value = getattr(config, config_var, None)
        if value and value != expected_placeholder:
            print(f"✅ {config_var}: Configured")
            return True
        else:
            print(f"⚠️  {config_var}: Not configured (placeholder detected)")
            return False
    except ImportError:
        print(f"❌ config.py: Not found")
        return False

def main():
    print("🔍 Verifying Setup...\n")
    
    # Check critical files
    files_ok = True
    files_ok &= check_file_exists("config.py", "Configuration file")
    files_ok &= check_file_exists("config.py.example", "Config example")
    files_ok &= check_file_exists("config/profiles.yaml", "Agent profiles")
    files_ok &= check_file_exists(".gitignore", "Git ignore file")
    
    # Check MCP servers
    print("\n📦 MCP Servers:")
    mcp_servers = [
        "mcp_server_1.py",
        "mcp_server_2.py",
        "mcp_server_3.py",
        "mcp_server_4_googlesheets.py",
        "mcp_server_5_gmail.py",
        "mcp_server_6_telegram.py",
    ]
    
    for server in mcp_servers:
        files_ok &= check_file_exists(server, f"MCP Server: {server}")
    
    # Check other components
    print("\n🔧 Components:")
    components = [
        ("agent.py", "Main agent"),
        ("telegram_webhook.py", "Telegram webhook"),
        ("credentials_setup.py", "OAuth setup"),
        ("SETUP.md", "Setup guide"),
        ("README.md", "Documentation"),
    ]
    
    for file, desc in components:
        files_ok &= check_file_exists(file, desc)
    
    # Check config values
    print("\n⚙️  Configuration:")
    config_ok = True
    config_ok &= check_config_value("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
    config_ok &= check_config_value("SENDER_EMAIL", "your-email@gmail.com")
    config_ok &= check_config_value("RECEIVER_EMAIL", "receiver@gmail.com")
    config_ok &= check_config_value("GOOGLE_CREDENTIALS_PATH")
    
    # Check credentials
    print("\n🔐 Credentials:")
    creds_ok = True
    if os.path.exists("credentials"):
        print("✅ credentials/ directory exists")
        creds_ok &= check_file_exists("credentials/google_credentials.json", "Google service account")
    else:
        print("❌ credentials/ directory not found")
        creds_ok = False
    
    # Summary
    print("\n" + "="*50)
    print("📊 Summary:")
    print("="*50)
    
    if files_ok:
        print("✅ All files present")
    else:
        print("❌ Some files missing")
    
    if config_ok:
        print("✅ Configuration looks good")
    else:
        print("⚠️  Configuration needs attention")
        print("   → Edit config.py with your actual values")
    
    if creds_ok:
        print("✅ Credentials directory exists")
    else:
        print("❌ Credentials not set up")
        print("   → Create credentials/ directory")
        print("   → Download Google credentials JSON files")
    
    if files_ok and config_ok and creds_ok:
        print("\n🎉 Setup looks complete! You can start the application.")
        return 0
    else:
        print("\n⚠️  Setup incomplete. Please address the issues above.")
        print("\n📖 For detailed instructions, see SETUP.md")
        return 1

if __name__ == "__main__":
    sys.exit(main())

