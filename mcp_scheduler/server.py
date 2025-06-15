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
from typing import Dict, List, Any, Optional
import threading
import time
from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
import inspect

from mcp.server.fastmcp import FastMCP, Context

from .task import Task, TaskStatus, TaskType
from .scheduler import Scheduler
from .config import Config
from .utils import human_readable_cron

logger = logging.getLogger(__name__)

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
    """Custom FastMCP implementation that exposes a .app property for FastAPI mounting."""
    def __init__(self, *args, transport="sse", **kwargs):
        super().__init__(*args, **kwargs)
        self._transport = transport
        # Initialize app based on transport type immediately
        if transport == "sse":
            self.app = self.sse_app()
        elif transport == "streamable-http":
            self.app = self.streamable_http_app()
        else:
            self.app = None
        # Initialize tools list
        self.tools = []

    def tool(self, *args, **kwargs):
        """Override tool decorator to track registered tools."""
        def decorator(func):
            # Get the original tool decorator from the parent class
            original_tool = FastMCP.tool(self, *args, **kwargs)
            # Apply the original decorator
            tool = original_tool(func)
            # Add to our tools list
            if not hasattr(self, 'tools'):
                self.tools = []
            self.tools.append(tool)
            return tool
        return decorator

class SchedulerServer:
    """MCP server for task scheduling."""
    
    def __init__(self, scheduler: Scheduler, config: Config):
        """Initialize the MCP server."""
        self.scheduler = scheduler
        self.config = config
        
        # Configure Uvicorn logging and settings
        uvicorn.config.LOGGING_CONFIG["loggers"]["uvicorn"]["level"] = "WARNING"
        uvicorn.config.LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(message)s"
        
        # Create main FastAPI application
        self.app = FastAPI(
            title=self.config.server_name,
            version=self.config.server_version,
            description="MCP Scheduler with well-known endpoint"
        )
        
        # Create MCP server with custom response formatting
        self.mcp = CustomFastMCP(
            host=config.server_address,
            port=config.server_port,
            transport=config.transport
        )
        
        # Register tools first
        self._register_tools()
        
        # Mount MCP server at /mcp only if the FastAPI app is available
        if self.mcp.app:
            self.app.mount("/mcp", self.mcp.app)
        elif self.config.transport in ("sse", "streamable-http"):
            logger.error("MCP app not initialized - transport may not be supported")
            raise RuntimeError("MCP transport not supported")
        # For stdio transport, nothing is mounted and no exception is raised
        
        # Add well-known endpoint at root level
        @self.app.get("/.well-known/mcp-schema.json")
        async def well_known_handler(request: Request) -> JSONResponse:
            """Handle requests to the well-known endpoint."""
            try:
                if not hasattr(self.mcp, 'tools'):
                    logger.error("MCP tools not available")
                    return JSONResponse(
                        {"error": "MCP tools not available"},
                        status_code=503
                    )
                # Convert tools to schema
                mcp_tools = [tool_to_schema(tool) for tool in self.mcp.tools]
                # Build response
                response = {
                    "name": self.config.server_name,
                    "version": self.config.server_version,
                    "tools": mcp_tools,
                    "mcp_endpoint": f"/mcp"  # Add MCP endpoint location
                }
                return JSONResponse(response)
            except Exception as e:
                logger.error(f"Error in well-known handler: {e}")
                return JSONResponse(
                    {"error": "Internal server error"},
                    status_code=500
                )
        
        # nothing else to init

    def _register_tools(self):
        """Register MCP tools."""
        import logging
        logger = logging.getLogger(__name__)

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
