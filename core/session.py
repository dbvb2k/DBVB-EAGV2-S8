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
            try:
                # Check transport type
                transport = config.get("transport", "stdio")
                
                if transport == "sse":
                    await self._initialize_sse_server(config)
                else:
                    await self._initialize_stdio_server(config)
                    
            except Exception as e:
                print(f"❌ Error initializing MCP server {config.get('id', 'unknown')}: {e}")
                
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
        print(f"→ Connecting to SSE server: {base_url}")
        
        async with MCPSseClient(base_url) as sse_client:
            # Send initialize request
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
            
            # Get tools
            tools_message = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {}
            }
            
            response = await sse_client.send_message(tools_message)
            
            if response.get("result") and "tools" in response["result"]:
                tools = response["result"]["tools"]
                print(f"→ Tools received: {[tool['name'] for tool in tools]}")
                for tool_data in tools:
                    self.tool_map[tool_data["name"]] = {
                        "config": config,
                        "tool": tool_data
                    }

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
            message = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            response = await sse_client.send_message(message)
            
            if "error" in response:
                raise Exception(f"Tool call error: {response['error']}")
                
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