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

# Determine Python executable to use
def get_python_executable():
    """Get the Python executable, preferring venv if available."""
    venv_python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    # Fallback to current Python
    return sys.executable

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
    
    python_exe = get_python_executable()
    print(f"Using Python: {python_exe}\n")
    
    for server in SERVERS:
        print(f"Starting {server['name']} server on port {server['port']}...")
        try:
            process = subprocess.Popen(
                [python_exe, server["script"]],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine stderr with stdout
                text=True,  # Text mode for easier reading
                cwd=Path(__file__).parent
            )
            processes.append((server, process))
            print(f"✅ {server['name']} started (PID: {process.pid})")
        except Exception as e:
            print(f"❌ Failed to start {server['name']}: {e}")
    
    print("\n✅ All SSE servers started!")
    print(f"Running {len(processes)} servers in background.")
    print("\nPress Ctrl+C to stop all servers...\n")
    
    # Give servers a moment to start and show any immediate errors
    time.sleep(2)
    
    try:
        # Wait for processes and monitor output
        import threading
        import queue
        
        output_queues = {}
        
        def read_output(server_name, process, output_queue):
            """Read output from process in a separate thread."""
            try:
                for line in iter(process.stdout.readline, ''):
                    if line:
                        output_queue.put((server_name, line))
                process.stdout.close()
            except Exception as e:
                output_queue.put((server_name, f"Error reading output: {e}"))
        
        # Start output reader threads
        for server, process in processes:
            q = queue.Queue()
            output_queues[server['name']] = q
            thread = threading.Thread(
                target=read_output,
                args=(server['name'], process, q),
                daemon=True
            )
            thread.start()
        
        while True:
            time.sleep(0.5)
            # Check for output
            for server_name, q in output_queues.items():
                try:
                    while True:
                        name, line = q.get_nowait()
                        print(f"[{name}] {line.rstrip()}")
                except queue.Empty:
                    pass
            
            # Check if any process died
            for server, process in list(processes):
                if process.poll() is not None:
                    print(f"\n⚠️  {server['name']} server died! Exit code: {process.returncode}")
                    processes.remove((server, process))
                    # Read any remaining output
                    try:
                        remaining_output, _ = process.communicate(timeout=0.5)
                        if remaining_output:
                            print(f"Final output from {server['name']}:")
                            print(remaining_output)
                    except:
                        pass
            
            # If all processes died, exit
            if not processes:
                print("\n❌ All servers have stopped. Exiting.")
                break
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping all servers...")
        # Get all processes that are still running
        running_processes = [(s, p) for s, p in processes if p.poll() is None]
        for server, process in running_processes:
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

