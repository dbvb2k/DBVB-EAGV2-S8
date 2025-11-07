# core/session.py

import os
import sys
from typing import Optional, Any, List, Dict, Literal
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

# Import SSE client
try:
    from core.mcp_sse_client import MCPSseClient
    SSE_AVAILABLE = True
except ImportError:
    SSE_AVAILABLE = False
    MCPSseClient = None


class MCP:
    """
    Lightweight wrapper for one-time MCP tool calls using stdio transport.
    Each call spins up a new subprocess and terminates cleanly.
    """

    def __init__(
        self,
        server_script: str = "mcp_server_2.py",
        working_dir: Optional[str] = None,
        server_command: Optional[str] = None,
    ):
        self.server_script = server_script
        self.working_dir = working_dir or os.getcwd()
        self.server_command = server_command or sys.executable

    async def list_tools(self):
        server_params = StdioServerParameters(
            command=self.server_command,
            args=[self.server_script],
            cwd=self.working_dir
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                return tools_result.tools

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        server_params = StdioServerParameters(
            command=self.server_command,
            args=[self.server_script],
            cwd=self.working_dir
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool_name, arguments=arguments)


class MultiMCP:
    """
    Stateless version: discovers tools from multiple MCP servers, but reconnects per tool call.
    Each call_tool() uses a fresh session based on tool-to-server mapping.
    
    Supports both stdio and SSE transports based on server configuration.
    """

    def __init__(self, server_configs: List[dict]):
        self.server_configs = server_configs
        self.tool_map: Dict[str, Dict[str, Any]] = {}  # tool_name → {config, tool}

    async def initialize(self):
        print("in MultiMCP initialize")
        for config in self.server_configs:
            server_id = config.get('id', 'unknown')
            transport = config.get("transport", "stdio")
            try:
                # Check transport type
                if transport == "sse":
                    await self._initialize_sse_server(config)
                else:
                    await self._initialize_stdio_server(config)
                    
            except Exception as e:
                import traceback
                error_msg = f"❌ Error initializing MCP server {server_id} ({transport}): {e}"
                print(error_msg)
                print(f"Traceback: {traceback.format_exc()}")
                # Don't raise - continue with other servers, but log the error
                
    async def _initialize_stdio_server(self, config: dict):
        """Initialize stdio-based MCP server."""
        params = StdioServerParameters(
            command=sys.executable,
            args=[config["script"]],
            cwd=config.get("cwd", os.getcwd())
        )
        print(f"→ Scanning tools from: {config['script']} in {params.cwd}")
        async with stdio_client(params) as (read, write):
            print("Connection established, creating session...")
            try:
                async with ClientSession(read, write) as session:
                    print("[agent] Session created, initializing...")
                    await session.initialize()
                    print("[agent] MCP session initialized")
                    tools = await session.list_tools()
                    print(f"→ Tools received: {[tool.name for tool in tools.tools]}")
                    for tool in tools.tools:
                        self.tool_map[tool.name] = {
                            "config": config,
                            "tool": tool
                        }
            except Exception as se:
                print(f"❌ Session error: {se}")
                
    async def _initialize_sse_server(self, config: dict):
        """Initialize SSE-based MCP server."""
        if not SSE_AVAILABLE or not MCPSseClient:
            raise RuntimeError("SSE support not available. Install dependencies.")
            
        base_url = config.get("url", f"http://localhost:8000")
        server_id = config.get("id", "unknown")
        print(f"→ Connecting to SSE server {server_id}: {base_url}")
        
        try:
            async with MCPSseClient(base_url) as sse_client:
                # Send initialize request first
                init_message = {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "agent",
                            "version": "1.0.0"
                        }
                    }
                }
                
                print(f"→ Initializing SSE server {server_id}...")
                # Wait for initialization to complete
                init_response = await sse_client.send_message(init_message)
                if "error" in init_response:
                    error_detail = init_response.get("error", {})
                    error_msg = error_detail.get("message", str(error_detail))
                    raise RuntimeError(f"Initialization failed for {server_id}: {error_msg}")
                
                print(f"→ SSE server {server_id} initialized, sending notification...")
                # Now send initialized notification (required by MCP protocol)
                # Notifications don't have IDs and don't expect responses
                initialized_message = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {}
                }
                await sse_client.send_notification(initialized_message)
                
                # Get tools after initialization
                tools_message = {
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {}
                }
                
                print(f"→ Requesting tools from SSE server {server_id}...")
                response = await sse_client.send_message(tools_message)
                
                if "error" in response:
                    error_detail = response.get("error", {})
                    error_msg = error_detail.get("message", str(error_detail))
                    raise RuntimeError(f"Failed to get tools from {server_id}: {error_msg}")
                
                if response.get("result") and "tools" in response["result"]:
                    tools = response["result"]["tools"]
                    tool_names = [tool['name'] for tool in tools]
                    print(f"→ Tools received from {server_id}: {tool_names}")
                    for tool_data in tools:
                        self.tool_map[tool_data["name"]] = {
                            "config": config,
                            "tool": tool_data
                        }
                    print(f"→ Registered {len(tools)} tools from {server_id}")
                else:
                    print(f"⚠️  No tools received from {server_id}. Response: {response}")
                    raise RuntimeError(f"No tools found in response from {server_id}")
        except Exception as e:
            print(f"❌ Error in _initialize_sse_server for {server_id}: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            raise

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        entry = self.tool_map.get(tool_name)
        if not entry:
            raise ValueError(f"Tool '{tool_name}' not found on any server.")

        config = entry["config"]
        transport = config.get("transport", "stdio")
        
        if transport == "sse":
            return await self._call_tool_sse(config, tool_name, arguments)
        else:
            return await self._call_tool_stdio(config, tool_name, arguments)
            
    async def _call_tool_stdio(self, config: dict, tool_name: str, arguments: dict) -> Any:
        """Call tool via stdio transport."""
        params = StdioServerParameters(
            command=sys.executable,
            args=[config["script"]],
            cwd=config.get("cwd", os.getcwd())
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool_name, arguments)
                
    async def _call_tool_sse(self, config: dict, tool_name: str, arguments: dict) -> Any:
        """Call tool via SSE transport."""
        if not SSE_AVAILABLE or not MCPSseClient:
            raise RuntimeError("SSE support not available.")
            
        base_url = config.get("url", "http://localhost:8000")
        
        async with MCPSseClient(base_url) as sse_client:
            # Initialize the connection first
            init_message = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "agent",
                        "version": "1.0.0"
                    }
                }
            }
            
            init_response = await sse_client.send_message(init_message)
            if "error" in init_response:
                raise RuntimeError(f"Initialization failed: {init_response['error']}")
            
            # Send initialized notification
            initialized_message = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }
            await sse_client.send_notification(initialized_message)
            
            # Now call the tool
            message = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            try:
                response = await sse_client.send_message(message)
            except Exception as sse_error:
                # If SSE communication fails, provide more context
                error_msg = f"SSE communication error when calling {tool_name}: {sse_error}"
                print(f"[ERROR] {error_msg}")
                raise Exception(error_msg) from sse_error
            
            if "error" in response:
                error_info = response["error"]
                error_msg = error_info.get("message", str(error_info))
                error_code = error_info.get("code", "unknown")
                raise Exception(f"Tool call error ({error_code}): {error_msg}")
                
            # Convert to CallToolResult format
            result_data = response.get("result", {})
            if isinstance(result_data, dict):
                # Handle content list
                content = result_data.get("content", [])
                if content:
                    return CallToolResult(content=content, isError=result_data.get("isError", False))
                else:
                    # If no content, wrap response in TextContent
                    return CallToolResult(
                        content=[TextContent(type="text", text=str(result_data))],
                        isError=False
                    )
            else:
                # If result is not a dict, wrap it
                return CallToolResult(
                    content=[TextContent(type="text", text=str(result_data))],
                    isError=False
                )

    async def list_all_tools(self) -> List[str]:
        return list(self.tool_map.keys())

    def get_all_tools(self) -> List[Any]:
        return [entry["tool"] for entry in self.tool_map.values()]

    async def shutdown(self):
        pass  # no persistent sessions to close