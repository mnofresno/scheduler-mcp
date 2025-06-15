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
from typing import Dict, List, Any, Optional, Literal
import threading
import time
from fastapi import Request, FastAPI
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
    required = [k for k, v in params.items() if v.default is inspect.Parameter.empty and k != 'self']
    properties = {}
    for k, v in params.items():
        if k == 'self':
            continue
        param_type = str(v.annotation) if v.annotation != inspect.Parameter.empty else 'string'
        # Map Python types to JSON Schema types
        if param_type in ("<class 'int'>", 'int'):
            json_type = 'integer'
        elif param_type in ("<class 'bool'>", 'bool'):
            json_type = 'boolean'
        elif param_type in ("<class 'float'>", 'float'):
            json_type = 'number'
        elif param_type in ("<class 'dict'>", 'dict'):
            json_type = 'object'
        elif param_type in ("<class 'list'>", 'list'):
            json_type = 'array'
        else:
            json_type = 'string'
        properties[k] = {"type": json_type}
    return {
        "name": tool.__name__,
        "description": tool.__doc__ or "",
        "endpoint": tool.__name__,
        "method": "POST",
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False
        }
    }

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

class SchedulerServer:
    """MCP server for task scheduling."""
    
    def __init__(self, scheduler: Scheduler, config: Config):
        """Initialize the MCP server."""
        self.scheduler = scheduler
        self.config = config
        
        # Configure Uvicorn logging and settings
        uvicorn.config.LOGGING_CONFIG["loggers"]["uvicorn"]["level"] = "WARNING"
        uvicorn.config.LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(message)s"
        
        # Create main FastAPI application with enhanced metadata
        self.app = FastAPI(
            title=self.config.server_name,
            version=self.config.server_version,
            description="MCP Scheduler with well-known endpoint and SSE transport",
            docs_url="/api/docs",  # Move Swagger UI to /api/docs
            redoc_url="/api/redoc",  # Move ReDoc to /api/redoc
            openapi_url="/api/openapi.json",  # Move OpenAPI schema to /api/openapi.json
        )
        
        # Add middleware for request logging and CORS
        @self.app.middleware("http")
        async def log_requests(request: Request, call_next):
            if request.url.path == "/.well-known/mcp-schema.json":
                log_request(request, "Well-known schema request received", "info")
            response = await call_next(request)
            if request.url.path == "/.well-known/mcp-schema.json":
                log_request(request, f"Well-known schema request completed with status {response.status_code}", "info")
            return response
        
        # Create MCP server with custom response formatting
        self.mcp = CustomFastMCP(
            host=config.server_address,
            port=config.server_port
        )
        
        # Register tools first
        self._register_tools()
        logger.info(f"Tools registrados: {self.mcp.tools}")
        
        # Montar la app HTTP/SSE de FastMCP
        if self.config.transport in ("sse", "streamable-http"):
            try:
                mcp_app = self.mcp.http_app(
                    path="/mcp",
                    transport=self.config.transport,
                    middleware=[]  # Add any additional middleware here if needed
                )
                self.app.mount("/mcp", mcp_app)
                logger.info(f"MCP server mounted at /mcp with {config.transport} transport")
            except Exception as e:
                logger.error(f"Error mounting MCP app: {str(e)}", exc_info=True)
                raise RuntimeError(f"Failed to mount MCP app: {str(e)}")
        elif self.config.transport == "stdio":
            logger.info("MCP server running in stdio mode")
        else:
            logger.error(f"MCP app not initialized - transport '{config.transport}' not supported")
            raise RuntimeError(f"MCP transport '{config.transport}' not supported")
        
        # Add well-known endpoint at root level con log de tools
        @self.app.get("/.well-known/mcp-schema.json")
        async def well_known_handler(request: Request) -> JSONResponse:
            """Handle requests to the well-known endpoint."""
            try:
                logger.info(f"Tools disponibles en well-known: {self.mcp.tools}")
                if not self.mcp.tools:
                    log_request(request, "Well-known schema request failed - MCP tools not available", "error")
                    return JSONResponse(
                        status_code=503,
                        content={
                            "error": "Service Unavailable",
                            "message": "MCP tools not available"
                        }
                    )
                # Convert tools to schema
                mcp_tools = [tool_to_schema(tool) for tool in self.mcp.tools]
                # Build enhanced response
                response = {
                    "name": self.config.server_name,
                    "version": self.config.server_version,
                    "tools": mcp_tools,
                    "mcp_endpoint": "/mcp",  # Endpoint original
                    "transport": self.config.transport,
                    "server_info": {
                        "address": self.config.server_address,
                        "port": self.config.server_port,
                        "status": "running" if self.scheduler.active else "stopped"
                    }
                }
                log_request(request, "Well-known schema request successful", "info")
                return JSONResponse(response)
            except Exception as e:
                log_request(request, f"Well-known schema request failed with error: {str(e)}", "error")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Internal Server Error",
                        "message": str(e) if logger.isEnabledFor(logging.DEBUG) else "Schema generation error"
                    }
                )
        
        # nothing else to init

    def _register_tools(self):
        """Register MCP tools."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Ejecutando _register_tools() para MCP tools")

        @self.mcp.tool()
        async def list_tasks() -> List[Dict[str, Any]]:
            """List all scheduled tasks."""
            tasks = await self.scheduler.get_all_tasks()
            return [self._format_task_response(task) for task in tasks]

        @self.mcp.tool()
        async def get_task(task_id: str) -> Optional[Dict[str, Any]]:
            """Get details of a specific task.
            
            Args:
                task_id: ID of the task to retrieve
            """
            task = await self.scheduler.get_task(task_id)
            if not task:
                return None
            
            result = self._format_task_response(task)
            
            # Add execution history
            executions = await self.scheduler.get_task_executions(task_id)
            result["executions"] = [
                {
                    "id": exec.id,
                    "start_time": exec.start_time.isoformat(),
                    "end_time": exec.end_time.isoformat() if exec.end_time else None,
                    "status": exec.status.value,
                    "output": exec.output[:1000] if exec.output else None,  # Limit output size
                    "error": exec.error
                }
                for exec in executions
            ]
            
            return result
        
        @self.mcp.tool()
        async def add_command_task(
            name: str,
            schedule: str,
            command: str,
            description: Optional[str] = None,
            enabled: bool = True,
            do_only_once: bool = True  # New parameter with default True
        ) -> Dict[str, Any]:
            """Add a new shell command task."""
            task = Task(
                name=name,
                schedule=schedule,
                type=TaskType.SHELL_COMMAND,
                command=command,
                description=description,
                enabled=enabled,
                do_only_once=do_only_once  # Pass the new parameter
            )
            
            task = await self.scheduler.add_task(task)
            return self._format_task_response(task)
        
        @self.mcp.tool()
        async def add_api_task(
            name: str,
            schedule: str,
            api_url: str,
            api_method: str = "GET",
            api_headers: Optional[Dict[str, str]] = None,
            api_body: Optional[Dict[str, Any]] = None,
            description: Optional[str] = None,
            enabled: bool = True,
            do_only_once: bool = True  # New parameter with default True
        ) -> Dict[str, Any]:
            """Add a new API call task."""
            task = Task(
                name=name,
                schedule=schedule,
                type=TaskType.API_CALL,
                api_url=api_url,
                api_method=api_method,
                api_headers=api_headers,
                api_body=api_body,
                description=description,
                enabled=enabled,
                do_only_once=do_only_once  # Pass the new parameter
            )
            
            task = await self.scheduler.add_task(task)
            return self._format_task_response(task)
        
        @self.mcp.tool()
        async def add_ai_task(
            name: str,
            schedule: str,
            prompt: str,
            description: Optional[str] = None,
            enabled: bool = True,
            do_only_once: bool = True  # New parameter with default True
        ) -> Dict[str, Any]:
            """Add a new AI task."""
            task = Task(
                name=name,
                schedule=schedule,
                type=TaskType.AI,
                prompt=prompt,
                description=description,
                enabled=enabled,
                do_only_once=do_only_once  # Pass the new parameter
            )
            
            task = await self.scheduler.add_task(task)
            return self._format_task_response(task)

        @self.mcp.tool()
        async def add_reminder_task(
            name: str,
            schedule: str,
            message: str,
            title: Optional[str] = None,
            description: Optional[str] = None,
            enabled: bool = True,
            do_only_once: bool = True
        ) -> Dict[str, Any]:
            """Add a new reminder task that shows a popup notification with sound."""
            # Check if we have notification capabilities on this platform
            os_type = platform.system()
            has_notification_support = True
            
            if os_type == "Linux":
                # Check for notify-send or zenity
                try:
                    import shutil
                    notify_send_path = shutil.which("notify-send")
                    zenity_path = shutil.which("zenity")
                    if not notify_send_path and not zenity_path:
                        has_notification_support = False
                except ImportError:
                    # Can't check, we'll try anyway
                    pass
            
            if not has_notification_support:
                logger.warning(f"Platform {os_type} may not support notifications")
            
            task = Task(
                name=name,
                schedule=schedule,
                type=TaskType.REMINDER,
                description=description,
                enabled=enabled,
                do_only_once=do_only_once,
                reminder_title=title or name,
                reminder_message=message
            )
            
            task = await self.scheduler.add_task(task)
            return self._format_task_response(task)
        
        @self.mcp.tool()
        async def update_task(
            task_id: str,
            name: Optional[str] = None,
            schedule: Optional[str] = None,
            command: Optional[str] = None,
            api_url: Optional[str] = None,
            api_method: Optional[str] = None,
            api_headers: Optional[Dict[str, str]] = None,
            api_body: Optional[Dict[str, Any]] = None,
            prompt: Optional[str] = None,
            description: Optional[str] = None,
            enabled: Optional[bool] = None,
            do_only_once: Optional[bool] = None,  # New parameter
            reminder_title: Optional[str] = None, # New parameter for reminders
            reminder_message: Optional[str] = None # New parameter for reminders
        ) -> Optional[Dict[str, Any]]:
            """Update an existing task."""
            update_data = {}
            
            if name is not None:
                update_data["name"] = name
            if schedule is not None:
                update_data["schedule"] = schedule
            if command is not None:
                update_data["command"] = command
            if api_url is not None:
                update_data["api_url"] = api_url
            if api_method is not None:
                update_data["api_method"] = api_method
            if api_headers is not None:
                update_data["api_headers"] = api_headers
            if api_body is not None:
                update_data["api_body"] = api_body
            if prompt is not None:
                update_data["prompt"] = prompt
            if description is not None:
                update_data["description"] = description
            if enabled is not None:
                update_data["enabled"] = enabled
            if do_only_once is not None:
                update_data["do_only_once"] = do_only_once
            if reminder_title is not None:
                update_data["reminder_title"] = reminder_title
            if reminder_message is not None:
                update_data["reminder_message"] = reminder_message
            
            task = await self.scheduler.update_task(task_id, **update_data)
            if not task:
                return None
            
            return self._format_task_response(task)
        
        @self.mcp.tool()
        async def remove_task(task_id: str) -> bool:
            """Remove a task."""
            return await self.scheduler.delete_task(task_id)
        
        @self.mcp.tool()
        async def enable_task(task_id: str) -> Optional[Dict[str, Any]]:
            """Enable a task."""
            task = await self.scheduler.enable_task(task_id)
            if not task:
                return None
            
            return self._format_task_response(task)
        
        @self.mcp.tool()
        async def disable_task(task_id: str) -> Optional[Dict[str, Any]]:
            """Disable a task."""
            task = await self.scheduler.disable_task(task_id)
            if not task:
                return None
            
            return self._format_task_response(task)
        
        @self.mcp.tool()
        async def run_task_now(task_id: str) -> Optional[Dict[str, Any]]:
            """Run a task immediately."""
            execution = await self.scheduler.run_task_now(task_id)
            if not execution:
                return None
            
            task = await self.scheduler.get_task(task_id)
            if not task:
                return None
            
            result = self._format_task_response(task)
            result["execution"] = {
                "id": execution.id,
                "start_time": execution.start_time.isoformat(),
                "end_time": execution.end_time.isoformat() if execution.end_time else None,
                "status": execution.status.value,
                "output": execution.output[:1000] if execution.output else None,  # Limit output size
                "error": execution.error
            }
            
            return result
        
        @self.mcp.tool()
        async def get_task_executions(task_id: str, limit: int = 10) -> List[Dict[str, Any]]:
            """Get execution history for a task."""
            executions = await self.scheduler.get_task_executions(task_id, limit)
            return [
                {
                    "id": exec.id,
                    "task_id": exec.task_id,
                    "start_time": exec.start_time.isoformat(),
                    "end_time": exec.end_time.isoformat() if exec.end_time else None,
                    "status": exec.status.value,
                    "output": exec.output[:1000] if exec.output else None,  # Limit output size
                    "error": exec.error
                }
                for exec in executions
            ]
        
        @self.mcp.tool()
        async def get_server_info() -> Dict[str, Any]:
            """Get server information."""
            return {
                "name": self.config.server_name,
                "version": self.config.server_version,
                "scheduler_status": "running" if self.scheduler.active else "stopped",
                "check_interval": self.config.check_interval,
                "execution_timeout": self.config.execution_timeout,
                "ai_model": self.config.ai_model
            }

        logger.info(f"Tools después de registrar: {self.mcp.tools}")
        # Forzar inicialización manual si no existe
        if not self.mcp.tools:
            if hasattr(self.mcp, '_tools'):
                self.mcp.tools = list(self.mcp._tools.values())
                logger.info(f"Tools forzados manualmente: {self.mcp.tools}")

    def _format_task_response(self, task: Task) -> Dict[str, Any]:
        """Format a task for API response."""
        result = {
            "id": task.id,
            "name": task.name,
            "schedule": task.schedule,
            "schedule_human_readable": human_readable_cron(task.schedule),
            "type": task.type.value,
            "description": task.description,
            "enabled": task.enabled,
            "do_only_once": task.do_only_once,
            "status": task.status.value,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "last_run": task.last_run.isoformat() if task.last_run else None,
            "next_run": task.next_run.isoformat() if task.next_run else None
        }
        
        # Add type-specific fields
        if task.type == TaskType.SHELL_COMMAND:
            result["command"] = task.command
            
        elif task.type == TaskType.API_CALL:
            result["api_url"] = task.api_url
            result["api_method"] = task.api_method
            result["api_headers"] = task.api_headers
            # Don't include full API body to keep response size reasonable
            if task.api_body:
                result["api_body_keys"] = list(task.api_body.keys())
            
        elif task.type == TaskType.AI:
            result["prompt"] = task.prompt
            
        elif task.type == TaskType.REMINDER:
            result["reminder_title"] = task.reminder_title
            result["reminder_message"] = task.reminder_message
            
        return result
            
    def start(self):
        """Start the server."""
        if self.config.transport == "sse":
            # Set port via environment variable for Uvicorn
            os.environ["UVICORN_PORT"] = str(self.config.server_port)
            # Start the server using Uvicorn
            uvicorn.run(
                self.app,
                host=self.config.server_address,
                port=self.config.server_port,
                log_level="warning"
            )
        elif self.config.transport == "stdio":
            # For stdio transport, use run_stdio if available
            if hasattr(self.mcp, "run_stdio"):
                self.mcp.run_stdio()
            elif hasattr(self.mcp, "run"):
                self.mcp.run()
            else:
                raise RuntimeError("FastMCP does not support stdio in this version")
        else:
            # For other transports, use start if available
            if hasattr(self.mcp, "start"):
                self.mcp.start()
            else:
                raise RuntimeError("FastMCP does not support this transport in this version")
