# start_sse_servers.py - Start all SSE MCP servers

"""
Convenience script to start all SSE MCP servers in the background.
These servers need to be running for the agent to use SSE transport.
"""

import subprocess
import sys
import time
import os
from pathlib import Path

# Server configurations
SERVERS = [
    {
        "name": "Google Sheets",
        "script": "mcp_server_4_googlesheets.py",
        "port": 8100
    },
    {
        "name": "Gmail",
        "script": "mcp_server_5_gmail.py",
        "port": 8101
    },
    {
        "name": "Telegram",
        "script": "mcp_server_6_telegram.py",
        "port": 8102
    }
]

def start_servers():
    """Start all SSE servers."""
    processes = []
    
    print("🚀 Starting SSE MCP Servers...\n")
    
    for server in SERVERS:
        print(f"Starting {server['name']} server on port {server['port']}...")
        try:
            process = subprocess.Popen(
                [sys.executable, server["script"]],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=Path(__file__).parent
            )
            processes.append((server, process))
            print(f"✅ {server['name']} started (PID: {process.pid})")
        except Exception as e:
            print(f"❌ Failed to start {server['name']}: {e}")
    
    print("\n✅ All SSE servers started!")
    print(f"Running {len(processes)} servers in background.")
    print("\nPress Ctrl+C to stop all servers...\n")
    
    try:
        # Wait for processes
        while True:
            time.sleep(1)
            # Check if any process died
            for server, process in processes:
                if process.poll() is not None:
                    print(f"⚠️  {server['name']} server died! Exit code: {process.returncode}")
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping all servers...")
        for server, process in processes:
            print(f"Stopping {server['name']}...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            print(f"✅ {server['name']} stopped")
        print("\n✅ All servers stopped. Goodbye!")

if __name__ == "__main__":
    start_servers()

