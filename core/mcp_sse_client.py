# core/mcp_sse_client.py - MCP SSE Client Implementation

"""
Custom SSE client for connecting to MCP servers running with SSE transport.

MCP SSE transport uses:
- GET /sse to establish connection and receive session_id
- POST /messages/?session_id=... for sending requests  
- SSE stream for receiving responses
"""

import asyncio
import json
import httpx
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class MCPSseClient:
    """
    Client for connecting to MCP servers via SSE transport.
    
    Handles:
    - Establishing SSE connection and getting session_id
    - Sending POST requests to /messages/?session_id=...
    - Receiving SSE events from /sse
    - MCP protocol message handling
    """
    
    def __init__(self, base_url: str, sse_path: str = "/sse", message_path: str = "/messages/"):
        """
        Initialize MCP SSE client.
        
        Args:
            base_url: Base URL of the MCP server (e.g., "http://localhost:8100")
            sse_path: Path for SSE endpoint (default: "/sse")
            message_path: Path for POST messages (default: "/messages/")
        """
        self.base_url = base_url.rstrip('/')
        self.sse_url = f"{self.base_url}{sse_path}"
        self.message_path = message_path
        self._session: Optional[httpx.AsyncClient] = None
        self._sse_response: Optional[httpx.Response] = None
        self._sse_stream_context = None  # Keep reference to stream context
        self._session_id: Optional[str] = None
        self._session_id_event = asyncio.Event()  # Event to signal session_id received
        self._request_counter = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._sse_task: Optional[asyncio.Task] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self._session = httpx.AsyncClient()
        # Establish SSE connection and get session_id
        await self._connect_sse()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
        # Close SSE stream context if it exists
        if self._sse_stream_context:
            try:
                await self._sse_stream_context.__aexit__(exc_type, exc_val, exc_tb)
            except Exception:
                pass
        if self._session:
            await self._session.aclose()
            
    async def _connect_sse(self):
        """Establish SSE connection and receive session_id."""
        if not self._session:
            raise RuntimeError("Session not initialized.")
            
        logger.debug(f"Connecting to SSE endpoint: {self.sse_url}")
        
        try:
            # Get the stream context manager
            stream_context = self._session.stream('GET', self.sse_url)
            # Enter the context and get the response
            self._sse_stream_context = stream_context
            response = await stream_context.__aenter__()
            response.raise_for_status()
            self._sse_response = response
            
            # Start processing SSE stream in background
            self._sse_task = asyncio.create_task(self._process_sse_stream())
            
            # Wait for session_id to be received (with timeout)
            try:
                await asyncio.wait_for(self._session_id_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Failed to receive session_id from SSE server at {self.sse_url} within 5 seconds. "
                    "Make sure the server is running and accessible."
                )
            
            if not self._session_id:
                raise RuntimeError("Session ID event was set but session_id is still None")
                
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Could not connect to SSE server at {self.sse_url}. "
                f"Make sure the server is running. Error: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ConnectionError(
                f"SSE server returned error: {e.response.status_code} - {e.response.text}"
            ) from e
                    
    async def _process_sse_stream(self):
        """Process SSE stream and extract messages."""
        current_event = None
        try:
            async for line in self._sse_response.aiter_lines():
                if not line.strip():
                    continue
                    
                logger.debug(f"Received SSE line: {line}")
                
                # Track event type
                if line.startswith('event: '):
                    current_event = line[7:].strip()  # Remove 'event: ' prefix
                    continue
                elif line.startswith('data: '):
                    data = line[6:]  # Remove 'data: ' prefix
                    
                    # Handle endpoint event (contains session_id)
                    if current_event == 'endpoint' and 'session_id=' in data:
                        import re
                        match = re.search(r'session_id=([a-f0-9-]+)', data)
                        if match:
                            self._session_id = match.group(1)
                            logger.debug(f"Extracted session_id: {self._session_id}")
                            self._session_id_event.set()
                            current_event = None  # Reset event
                            continue
                    
                    # Handle message events (MCP protocol messages)
                    if current_event == 'message' or not current_event:
                        # Try to parse as JSON
                        try:
                            message = json.loads(data)
                            
                            # If this looks like an MCP response, try to match it
                            if isinstance(message, dict) and 'id' in message:
                                msg_id = message['id']
                                if msg_id in self._pending_requests:
                                    future = self._pending_requests[msg_id]
                                    if not future.done():
                                        future.set_result(message)
                                        logger.debug(f"Matched response for request {msg_id}")
                        except json.JSONDecodeError:
                            # Not JSON, might be plain text
                            logger.debug(f"Non-JSON data received: {data}")
                    
                    current_event = None  # Reset after processing data
                        
        except Exception as e:
            error_msg = f"SSE stream error: {e}"
            logger.error(error_msg)
            import traceback
            logger.error(f"SSE stream traceback: {traceback.format_exc()}")
            # Cancel all pending requests
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(e)
                    
    async def send_notification(self, message: Dict[str, Any]) -> None:
        """
        Send a notification to the MCP server (no response expected).
        
        Args:
            message: MCP protocol notification message (dict, should not have 'id')
        """
        if not self._session:
            raise RuntimeError("Session not initialized. Use async context manager.")
            
        if not self._session_id:
            raise RuntimeError("No session_id available. SSE connection not established.")
        
        # Notifications should not have an ID - create a copy without it
        notification = {k: v for k, v in message.items() if k != 'id'}
        if 'id' in message:
            logger.warning("Notification message had 'id' field, removed it")
        
        # Send POST request with notification to session-specific endpoint
        message_url = f"{self.base_url}{self.message_path}?session_id={self._session_id}"
        
        logger.debug(f"Sending notification POST to {message_url}: {notification}")
        response = await self._session.post(
            message_url,
            json=notification,
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()
        logger.debug(f"Notification POST response status: {response.status_code}")
    
    async def send_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a message to the MCP server and wait for response.
        
        Args:
            message: MCP protocol message (dict)
            
        Returns:
            Response message from server
        """
        if not self._session:
            raise RuntimeError("Session not initialized. Use async context manager.")
            
        if not self._session_id:
            raise RuntimeError("No session_id available. SSE connection not established.")
            
        self._request_counter += 1
        request_id = self._request_counter
        
        # Prepare future for response
        response_future = asyncio.Future()
        self._pending_requests[request_id] = response_future
        
        try:
            # Add ID to message if not present
            if 'id' not in message:
                message['id'] = request_id
                
            # Send POST request with message to session-specific endpoint
            message_url = f"{self.base_url}{self.message_path}?session_id={self._session_id}"
            
            logger.debug(f"Sending POST to {message_url}: {message}")
            response = await self._session.post(
                message_url,
                json=message,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            logger.debug(f"POST response status: {response.status_code}")
            
            # Wait for response via SSE
            result = await asyncio.wait_for(response_future, timeout=30.0)
            return result
            
        except asyncio.TimeoutError:
            raise TimeoutError(f"Request {request_id} timed out")
        finally:
            # Clean up pending request
            self._pending_requests.pop(request_id, None)


async def connect_to_mcp_sse(base_url: str, sse_path: str = "/sse", message_path: str = "/messages/"):
    """
    Convenience function to create and connect to MCP SSE server.
    
    Usage:
        async with connect_to_mcp_sse("http://localhost:8000") as client:
            # Use client here
    """
    return MCPSseClient(base_url, sse_path, message_path)

