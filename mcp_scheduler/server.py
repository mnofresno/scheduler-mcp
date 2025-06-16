"""
Enhanced MCP server implementation for MCP Scheduler.
"""
import logging
import sys
import json
import re
import platform
import os
import asyncio
import uvicorn
import uvicorn.config
from typing import Dict, List, Any, Optional, Literal, Union
import threading
import time
from fastapi import Request, FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
import inspect
from datetime import datetime
from fastmcp import FastMCP
from fastmcp.server.http import StarletteWithLifespan, create_sse_app, SseServerTransport
from fastmcp.utilities.logging import get_logger
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send
from contextlib import asynccontextmanager
from starlette.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
import uuid

from .task import Task, TaskStatus, TaskType
from .scheduler import Scheduler
from .config import Config
from .utils import human_readable_cron

logger = get_logger(__name__)

def log_request(request: Request, message: str, level: str = "info"):
    """Log request details with timestamp and client info."""
    client_host = request.client.host if request.client else "unknown"
    timestamp = datetime.utcnow().isoformat()
    log_message = f"[{timestamp}] {message} - Client: {client_host} - Path: {request.url.path}"
    
    if level == "info":
        logger.info(log_message)
    elif level == "error":
        logger.error(log_message)
    elif level == "warning":
        logger.warning(log_message)
    elif level == "debug":
        logger.debug(log_message)

def tool_to_schema(tool):
    """Serialize a tool (function) to a schema dict for the well-known endpoint."""
    sig = inspect.signature(tool)
    params = sig.parameters
    return_type = sig.return_annotation
    
    # Get required parameters (excluding self)
    required = [k for k, v in params.items() if v.default is inspect.Parameter.empty and k != 'self']
    
    # Process parameters
    properties = {}
    for k, v in params.items():
        if k == 'self':
            continue
            
        # Get parameter type and description
        param_type = v.annotation
        param_doc = inspect.getdoc(tool) or ""
        param_desc = ""
        
        # Extract parameter description from docstring
        if param_doc:
            # Look for Args section in docstring
            args_section = re.search(r'Args:\s*\n\s*' + re.escape(k) + r':\s*(.*?)(?:\n\s*\w+:|$)', param_doc, re.DOTALL)
            if args_section:
                param_desc = args_section.group(1).strip()
        
        # Convert Python type to JSON Schema type
        json_type, json_format = _python_type_to_json_schema(param_type)
        
        # Build property schema
        prop_schema = {
            "type": json_type,
            "description": param_desc
        }
        
        # Add format if available
        if json_format:
            prop_schema["format"] = json_format
            
        # Add enum for specific parameters
        if k == "api_method":
            prop_schema["enum"] = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        elif k == "schedule":
            prop_schema["pattern"] = r"^(\*|[0-9]{1,2}|\*\/[0-9]{1,2})(\s+(\*|[0-9]{1,2}|\*\/[0-9]{1,2})){4}$"
            prop_schema["description"] = "Cron expression (minute hour day month weekday)"
            
        properties[k] = prop_schema
    
    # Process return type
    return_schema = _python_type_to_json_schema(return_type)[0]
    
    # Build tool schema
    schema = {
        "name": tool.__name__,
        "description": inspect.getdoc(tool) or "",
        "endpoint": tool.__name__,
        "method": "POST",
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False
        },
        "returns": {
            "type": return_schema,
            "description": f"Returns {return_type.__name__ if hasattr(return_type, '__name__') else str(return_type)}"
        }
    }
    
    # Add examples if available in docstring
    examples = re.search(r'Examples:\s*\n\s*```(.*?)```', inspect.getdoc(tool) or "", re.DOTALL)
    if examples:
        try:
            schema["examples"] = json.loads(examples.group(1))
        except:
            pass
            
    return schema

def _python_type_to_json_schema(py_type):
    """Convert Python type to JSON Schema type and format."""
    # Handle Optional types
    if hasattr(py_type, "__origin__") and py_type.__origin__ is Union:
        # Get the non-None type from Optional[T]
        types = [t for t in py_type.__args__ if t is not type(None)]
        if types:
            return _python_type_to_json_schema(types[0])
        return "string", None
        
    # Handle List types
    if hasattr(py_type, "__origin__") and py_type.__origin__ is list:
        item_type, _ = _python_type_to_json_schema(py_type.__args__[0])
        return "array", {"items": {"type": item_type}}
        
    # Handle Dict types
    if hasattr(py_type, "__origin__") and py_type.__origin__ is dict:
        return "object", None
        
    # Handle basic types
    if py_type == str or py_type == "str":
        return "string", None
    elif py_type == int or py_type == "int":
        return "integer", None
    elif py_type == float or py_type == "float":
        return "number", None
    elif py_type == bool or py_type == "bool":
        return "boolean", None
    elif py_type == datetime:
        return "string", "date-time"
    elif py_type == Any:
        return "object", None
        
    # Default to string for unknown types
    return "string", None

class EnhancedJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that ensures arrays have proper comma separation."""
    def encode(self, obj):
        if isinstance(obj, (list, tuple)):
            if not obj:  # Empty list/tuple
                return '[]'
            # Ensure proper comma separation for arrays
            items = [self.encode(item) for item in obj]
            return '[' + ','.join(items) + ']'
        return super().encode(obj)

class CustomFastMCP(FastMCP):
    """Custom FastMCP server with enhanced logging."""
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._sse_transport = None
        self._tools = {}  # Initialize tools dictionary
        
    def http_app(
        self,
        path: str | None = None,
        middleware: list[Middleware] | None = None,
        transport: Literal["streamable-http", "sse"] = "streamable-http",
    ) -> StarletteWithLifespan:
        """Create a Starlette app using the specified HTTP transport with enhanced logging."""
        
        if transport == "sse":
            # Initialize SSE transport with logging and custom path
            base_path = path or "/api/mcp"
            self._sse_transport = SseServerTransport(f"{base_path}/messages")
            
            # Create a custom SSE handler with enhanced logging
            async def handle_sse(scope: Scope, receive: Receive, send: Send) -> Response:
                client_info = {
                    "host": scope.get("client", ("unknown", 0))[0],
                    "headers": dict(scope.get("headers", [])),
                    "query_params": dict(scope.get("query_string", b"").decode().split("&") if scope.get("query_string") else []),
                    "path": scope.get("path", "unknown"),
                }
                logger.info(f"New SSE connection established from {client_info}")
                start_time = time.time()
                
                try:
                    async with self._sse_transport.connect_sse(scope, receive, send) as streams:
                        await self._mcp_server.run(
                            streams[0],
                            streams[1],
                            self._mcp_server.create_initialization_options(),
                        )
                    duration = time.time() - start_time
                    logger.info(f"SSE connection closed after {duration:.2f}s from {client_info}")
                    return Response()
                except Exception as e:
                    duration = time.time() - start_time
                    logger.error(f"SSE connection error after {duration:.2f}s from {client_info}: {str(e)}", exc_info=True)
                    return JSONResponse(
                        status_code=500,
                        content={
                            "error": "Internal Server Error",
                            "message": str(e) if logger.isEnabledFor(logging.DEBUG) else "Connection error"
                        }
                    )
                    
            # Create a custom message handler with enhanced logging
            async def handle_post_message(scope: Scope, receive: Receive, send: Send) -> None:
                request = Request(scope, receive)
                client_info = {
                    "host": scope.get("client", ("unknown", 0))[0],
                    "headers": dict(scope.get("headers", [])),
                    "query_params": dict(scope.get("query_string", b"").decode().split("&") if scope.get("query_string") else []),
                    "path": scope.get("path", "unknown"),
                }
                logger.info(f"Received POST message from {client_info}")
                
                try:
                    await self._sse_transport.handle_post_message(scope, receive, send)
                    logger.info(f"Successfully processed POST message from {client_info}")
                except Exception as e:
                    logger.error(f"Error processing POST message from {client_info}: {str(e)}", exc_info=True)
                    return JSONResponse(
                        status_code=500,
                        content={
                            "error": "Internal Server Error",
                            "message": str(e) if logger.isEnabledFor(logging.DEBUG) else "Message processing error"
                        }
                    )
                    
            # Create the app with our custom handlers and enhanced middleware
            app = create_sse_app(
                server=self,
                message_path=f"{base_path}/messages",
                sse_path=f"{base_path}/sse",
                auth=self.auth,
                debug=False,  # Disable debug mode for production
                middleware=middleware or [],
            )
            
            # Replace the default handlers with our custom ones
            for route in app.routes:
                if route.path == f"{base_path}/sse":
                    route.endpoint = handle_sse
                elif route.path == f"{base_path}/messages":
                    route.app = handle_post_message
                    
            return app
            
        else:
            # Use the default implementation for other transports
            return super().http_app(
                path=path,
                middleware=middleware,
                transport=transport,
            )

    def tool(self, *args, **kwargs):
        """Custom tool decorator that ensures tools are properly registered."""
        def decorator(func):
            tool_name = func.__name__
            # Register the tool in our local dictionary
            self._tools[tool_name] = func
            # Use the parent class's tool decorator
            decorated_func = FastMCP.tool(self, *args, **kwargs)(func)
            return decorated_func
        return decorator

    @property
    def tools(self):
        """Get the list of registered tools."""
        # First try to get tools from parent class
        parent_tools = super().tools if hasattr(super(), 'tools') else []
        # Then combine with our local tools
        local_tools = list(self._tools.values())
        # Return unique tools (avoid duplicates)
        return list({tool.__name__: tool for tool in parent_tools + local_tools}.values())

class McpScheduler:
    def __init__(self):
        self.app = FastAPI(title="MCP Scheduler")
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.setup_middleware()
        self.setup_routes()

    def setup_middleware(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def setup_routes(self):
        @self.app.get("/.well-known/mcp-schema.json")
        async def get_schema():
            return {
                "mcp_endpoint": "/mcp",
                "transport": "http",
                "tools": [
                    {
                        "name": "schedule_task",
                        "description": "Schedule a task to be executed at a specific time",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task_name": {
                                    "type": "string",
                                    "description": "Name of the task to schedule"
                                },
                                "execution_time": {
                                    "type": "string",
                                    "description": "Time when the task should be executed (ISO format)"
                                },
                                "parameters": {
                                    "type": "object",
                                    "description": "Parameters for the task"
                                }
                            },
                            "required": ["task_name", "execution_time"]
                        }
                    }
                ]
            }

        @self.app.get("/mcp/sse")
        async def sse_endpoint(request_id: str, session_id: str):
            if not session_id:
                raise HTTPException(status_code=400, detail="Session ID is required")

            async def event_generator():
                try:
                    # Create a new session
                    self.sessions[session_id] = {
                        "request_id": request_id,
                        "created_at": datetime.utcnow(),
                        "messages": [],
                        "status": "connected"
                    }
                    
                    # Send the endpoint for POST messages
                    yield f"data: {json.dumps({'type': 'endpoint', 'data': '/mcp/messages'})}\n\n"
                    
                    # Keep the connection alive
                    while True:
                        await asyncio.sleep(30)
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                        
                except Exception as e:
                    logger.error(f"Error in SSE connection: {str(e)}")
                    if session_id in self.sessions:
                        del self.sessions[session_id]
                    raise

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        @self.app.post("/mcp/messages")
        async def process_message(request: Request, background_tasks: BackgroundTasks):
            try:
                data = await request.json()
                session_id = data.get("session_id")
                request_id = data.get("request_id")
                tool = data.get("tool")
                args = data.get("args", {})

                if not session_id:
                    raise HTTPException(status_code=400, detail="Session ID is required")

                if session_id not in self.sessions:
                    raise HTTPException(status_code=404, detail="Session not found")

                session = self.sessions[session_id]
                if session["request_id"] != request_id:
                    raise HTTPException(status_code=400, detail="Request ID mismatch")

                # Process the message in the background
                background_tasks.add_task(self.process_tool_request, session_id, tool, args)

                return JSONResponse({
                    "status": "accepted",
                    "message": "Request is being processed"
                })

            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))

    async def process_tool_request(self, session_id: str, tool: str, args: Dict[str, Any]):
        try:
            session = self.sessions.get(session_id)
            if not session:
                logger.error(f"Session {session_id} not found")
                return

            if tool == "schedule_task":
                # Process the scheduling request
                task_name = args.get("task_name")
                execution_time = args.get("execution_time")
                parameters = args.get("parameters", {})

                # Here you would implement the actual task scheduling logic
                # For now, we'll just simulate a successful response
                await asyncio.sleep(2)  # Simulate processing time

                # Send success response
                session["messages"].append({
                    "type": "result",
                    "result": {
                        "status": "scheduled",
                        "task_id": str(uuid.uuid4()),
                        "task_name": task_name,
                        "execution_time": execution_time
                    }
                })

            else:
                # Send error for unknown tool
                session["messages"].append({
                    "type": "error",
                    "error": f"Unknown tool: {tool}"
                })

        except Exception as e:
            logger.error(f"Error processing tool request: {str(e)}")
            if session_id in self.sessions:
                session = self.sessions[session_id]
                session["messages"].append({
                    "type": "error",
                    "error": str(e)
                })

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        uvicorn.run(self.app, host=host, port=port)

if __name__ == "__main__":
    scheduler = McpScheduler()
    scheduler.run()
