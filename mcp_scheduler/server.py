"""
MCP server implementation for MCP Scheduler.
"""
import logging
import json
import asyncio
import uvicorn
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from fastapi import Request, FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .task import Task, TaskStatus, TaskType, TaskExecution
from .scheduler import Scheduler
from .config import Config
from .persistence import Database
from .executor import Executor

logger = logging.getLogger(__name__)

class McpScheduler:
    def __init__(self):
        self.config = Config()
        self.app = FastAPI(
            title=self.config.server_name,
            version=self.config.server_version
        )
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.pending_ai_tasks: Dict[str, Dict[str, Any]] = {}  # task_id -> task_info
        self.database = Database(self.config.db_path)
        self.executor = Executor(self.config)
        self.scheduler = Scheduler(self.database, self.executor)
        self.setup_middleware()
        self.setup_routes()
        self.start_scheduler()
        self.start_session_cleanup()
        self.start_ai_task_cleanup()
        self.start_health_check()
        self.start_performance_monitoring()
        self.start_metrics_collection()
        self.start_error_recovery()

    def setup_middleware(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def start_scheduler(self):
        async def run_scheduler():
            retry_count = 0
            max_retries = 5
            while retry_count < max_retries:
                try:
                    await self.scheduler.start()
                    logger.info("Scheduler started successfully")
                    return
                except Exception as e:
                    retry_count += 1
                    logger.error(f"Error starting scheduler (attempt {retry_count}/{max_retries}): {str(e)}")
                    if retry_count < max_retries:
                        await asyncio.sleep(5 * retry_count)  # Exponential backoff
                    else:
                        logger.critical("Failed to start scheduler after maximum retries")
                        raise

        asyncio.create_task(run_scheduler())

    def start_session_cleanup(self):
        async def cleanup_expired_sessions():
            while True:
                try:
                    now = datetime.now(UTC)
                    expired_sessions = [
                        session_id for session_id, session in self.sessions.items()
                        if now - session["last_heartbeat"] > timedelta(seconds=self.config.session_timeout)
                    ]
                    
                    for session_id in expired_sessions:
                        logger.info(f"Cleaning up expired session: {session_id}")
                        # Notificar a otros clientes sobre la desconexión
                        self.broadcast_message({
                            "type": "session_disconnected",
                            "session_id": session_id,
                            "timestamp": now.isoformat()
                        }, exclude={session_id})
                        del self.sessions[session_id]
                    
                    await asyncio.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Error in session cleanup: {str(e)}")
                    await asyncio.sleep(60)

        asyncio.create_task(cleanup_expired_sessions())

    def start_ai_task_cleanup(self):
        async def cleanup_expired_ai_tasks():
            while True:
                try:
                    now = datetime.now(UTC)
                    expired_tasks = [
                        task_id for task_id, task_info in self.pending_ai_tasks.items()
                        if now - task_info["request_time"] > timedelta(seconds=self.config.execution_timeout)
                    ]
                    
                    for task_id in expired_tasks:
                        logger.warning(f"AI task {task_id} expired without response")
                        task_info = self.pending_ai_tasks.pop(task_id)
                        
                        # Crear ejecución fallida
                        execution = TaskExecution(
                            task_id=task_id,
                            start_time=task_info["request_time"],
                            end_time=now,
                            status=TaskStatus.FAILED,
                            output=f"Task expired after {self.config.execution_timeout} seconds"
                        )
                        self.database.save_execution(execution)
                        
                        # Notificar a todos los clientes
                        self.broadcast_message({
                            "type": "ai_task_failed",
                            "task_id": task_id,
                            "execution_id": execution.id,
                            "error": "Task execution timed out",
                            "timestamp": now.isoformat()
                        })
                    
                    await asyncio.sleep(30)  # Check every 30 seconds
                except Exception as e:
                    logger.error(f"Error in AI task cleanup: {str(e)}")
                    await asyncio.sleep(30)

        asyncio.create_task(cleanup_expired_ai_tasks())

    def start_health_check(self):
        async def check_health():
            while True:
                try:
                    # Verificar estado del scheduler
                    if not self.scheduler.is_running():
                        logger.warning("Scheduler is not running, attempting to restart")
                        await self.scheduler.start()

                    # Verificar conexiones de base de datos
                    if not self.database.is_connected():
                        logger.warning("Database connection lost, attempting to reconnect")
                        self.database.reconnect()

                    # Verificar tareas pendientes
                    now = datetime.now(UTC)
                    for task_id, task_info in list(self.pending_ai_tasks.items()):
                        if now - task_info["request_time"] > timedelta(seconds=self.config.execution_timeout * 2):
                            logger.error(f"AI task {task_id} has been pending for too long, forcing cleanup")
                            await self.force_cleanup_ai_task(task_id)

                    await asyncio.sleep(300)  # Check every 5 minutes
                except Exception as e:
                    logger.error(f"Error in health check: {str(e)}")
                    await asyncio.sleep(300)

        asyncio.create_task(check_health())

    def start_performance_monitoring(self):
        async def monitor_performance():
            while True:
                try:
                    # Monitorear número de sesiones activas
                    active_sessions = len([s for s in self.sessions.values() if s["status"] == "connected"])
                    if active_sessions > 100:  # Ajustar según necesidades
                        logger.warning(f"High number of active sessions: {active_sessions}")

                    # Monitorear tareas de IA pendientes
                    pending_ai_tasks = len(self.pending_ai_tasks)
                    if pending_ai_tasks > 50:  # Ajustar según necesidades
                        logger.warning(f"High number of pending AI tasks: {pending_ai_tasks}")

                    # Monitorear uso de memoria
                    import psutil
                    process = psutil.Process()
                    memory_info = process.memory_info()
                    if memory_info.rss > 500 * 1024 * 1024:  # 500MB
                        logger.warning(f"High memory usage: {memory_info.rss / 1024 / 1024:.2f}MB")

                    await asyncio.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Error in performance monitoring: {str(e)}")
                    await asyncio.sleep(60)

        asyncio.create_task(monitor_performance())

    def start_metrics_collection(self):
        async def collect_metrics():
            while True:
                try:
                    # Recolectar métricas de tareas
                    tasks = await self.scheduler.get_all_tasks()
                    task_metrics = {
                        "total": len(tasks),
                        "by_type": {},
                        "by_status": {}
                    }
                    
                    for task in tasks:
                        # Métricas por tipo
                        task_type = task.type.value
                        task_metrics["by_type"][task_type] = task_metrics["by_type"].get(task_type, 0) + 1
                        
                        # Métricas por estado
                        task_status = task.status.value
                        task_metrics["by_status"][task_status] = task_metrics["by_status"].get(task_status, 0) + 1

                    # Recolectar métricas de ejecuciones
                    executions = self.database.get_recent_executions(limit=1000)
                    execution_metrics = {
                        "total": len(executions),
                        "by_status": {},
                        "avg_duration": 0
                    }
                    
                    total_duration = 0
                    for execution in executions:
                        # Métricas por estado
                        exec_status = execution.status.value
                        execution_metrics["by_status"][exec_status] = execution_metrics["by_status"].get(exec_status, 0) + 1
                        
                        # Duración promedio
                        if execution.end_time and execution.start_time:
                            duration = (execution.end_time - execution.start_time).total_seconds()
                            total_duration += duration
                    
                    if executions:
                        execution_metrics["avg_duration"] = total_duration / len(executions)

                    # Recolectar métricas de sesiones
                    session_metrics = {
                        "total": len(self.sessions),
                        "active": len([s for s in self.sessions.values() if s["status"] == "connected"]),
                        "avg_lifetime": 0
                    }
                    
                    total_lifetime = 0
                    for session in self.sessions.values():
                        if session["status"] == "connected":
                            lifetime = (datetime.now(UTC) - session["created_at"]).total_seconds()
                            total_lifetime += lifetime
                    
                    if session_metrics["active"]:
                        session_metrics["avg_lifetime"] = total_lifetime / session_metrics["active"]

                    # Logging de métricas
                    logger.info("System metrics:")
                    logger.info(f"Tasks: {json.dumps(task_metrics, indent=2)}")
                    logger.info(f"Executions: {json.dumps(execution_metrics, indent=2)}")
                    logger.info(f"Sessions: {json.dumps(session_metrics, indent=2)}")

                    await asyncio.sleep(300)  # Collect every 5 minutes
                except Exception as e:
                    logger.error(f"Error collecting metrics: {str(e)}")
                    await asyncio.sleep(300)

        asyncio.create_task(collect_metrics())

    def start_error_recovery(self):
        async def recover_from_errors():
            while True:
                try:
                    # Verificar y recuperar tareas fallidas
                    failed_tasks = await self.scheduler.get_failed_tasks()
                    for task in failed_tasks:
                        if task.retry_count < 3:  # Máximo 3 intentos
                            logger.info(f"Retrying failed task {task.id}")
                            await self.scheduler.retry_task(task.id)
                        else:
                            logger.error(f"Task {task.id} failed permanently after 3 attempts")

                    # Verificar y recuperar sesiones inestables
                    unstable_sessions = [
                        session_id for session_id, session in self.sessions.items()
                        if session["status"] == "connected" and
                        datetime.now(UTC) - session["last_heartbeat"] > timedelta(seconds=self.config.session_timeout / 2)
                    ]
                    for session_id in unstable_sessions:
                        logger.warning(f"Session {session_id} appears unstable, attempting recovery")
                        self.sessions[session_id]["status"] = "recovering"
                        self.broadcast_message({
                            "type": "session_recovery",
                            "session_id": session_id,
                            "timestamp": datetime.now(UTC).isoformat()
                        })

                    # Verificar y recuperar tareas de IA bloqueadas
                    blocked_ai_tasks = [
                        task_id for task_id, task_info in self.pending_ai_tasks.items()
                        if datetime.now(UTC) - task_info["request_time"] > timedelta(seconds=self.config.execution_timeout / 2)
                    ]
                    for task_id in blocked_ai_tasks:
                        logger.warning(f"AI task {task_id} appears blocked, attempting recovery")
                        await self.force_cleanup_ai_task(task_id)

                    await asyncio.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Error in error recovery: {str(e)}")
                    await asyncio.sleep(60)

        asyncio.create_task(recover_from_errors())

    async def force_cleanup_ai_task(self, task_id: str):
        """Fuerza la limpieza de una tarea de IA pendiente."""
        try:
            if task_id in self.pending_ai_tasks:
                task_info = self.pending_ai_tasks.pop(task_id)
                now = datetime.now(UTC)
                
                execution = TaskExecution(
                    task_id=task_id,
                    start_time=task_info["request_time"],
                    end_time=now,
                    status=TaskStatus.FAILED,
                    output="Task forcefully cleaned up due to extended pending time"
                )
                self.database.save_execution(execution)
                
                self.broadcast_message({
                    "type": "ai_task_failed",
                    "task_id": task_id,
                    "execution_id": execution.id,
                    "error": "Task forcefully cleaned up",
                    "timestamp": now.isoformat()
                })
        except Exception as e:
            logger.error(f"Error in force cleanup of AI task {task_id}: {str(e)}")

    def broadcast_message(self, message: Dict[str, Any], exclude: Set[str] = None):
        """Envía un mensaje a todos los clientes conectados excepto los excluidos."""
        exclude = exclude or set()
        for session_id, session in self.sessions.items():
            if session_id not in exclude and session["status"] == "connected":
                session["messages"].append(message)

    def setup_routes(self):
        @self.app.get("/.well-known/mcp-schema.json")
        async def get_schema():
            return {
                "mcp_endpoint": "/mcp",
                "transport": self.config.transport,
                "version": self.config.server_version,
                "tools": [
                    {
                        "name": "schedule_task",
                        "description": "Schedule a task to be executed at a specific time",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "schedule": {"type": "string"},
                                "type": {"type": "string", "enum": ["shell_command", "api_call", "ai", "reminder"]},
                                "command": {"type": "string"},
                                "api_url": {"type": "string"},
                                "api_method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]},
                                "api_headers": {"type": "object"},
                                "api_body": {"type": "object"},
                                "prompt": {"type": "string"},
                                "reminder_message": {"type": "string"},
                                "reminder_title": {"type": "string"},
                                "do_only_once": {"type": "boolean"},
                                "enabled": {"type": "boolean"}
                            },
                            "required": ["name", "schedule", "type"]
                        }
                    },
                    {
                        "name": "list_tasks",
                        "description": "List all scheduled tasks",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "status": {"type": "string", "enum": ["pending", "running", "completed", "failed", "disabled", "all"]},
                                "type": {"type": "string", "enum": ["shell_command", "api_call", "ai", "reminder", "all"]}
                            }
                        }
                    },
                    {
                        "name": "run_task",
                        "description": "Run a task immediately",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task_id": {"type": "string"}
                            },
                            "required": ["task_id"]
                        }
                    },
                    {
                        "name": "execute_ai_task",
                        "description": "Execute an AI task and return the result",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task_id": {"type": "string"},
                                "prompt": {"type": "string"},
                                "result": {"type": "string"}
                            },
                            "required": ["task_id", "prompt", "result"]
                        }
                    }
                ]
            }

        @self.app.get("/mcp/sse")
        async def sse_endpoint(request: Request, session_id: str):
            if not session_id:
                raise HTTPException(status_code=400, detail="Session ID is required")

            async def event_generator():
                try:
                    self.sessions[session_id] = {
                        "created_at": datetime.now(UTC),
                        "messages": [],
                        "status": "connected",
                        "last_heartbeat": datetime.now(UTC)
                    }
                    
                    # Notificar a otros clientes sobre la nueva conexión
                    self.broadcast_message({
                        "type": "session_connected",
                        "session_id": session_id,
                        "timestamp": datetime.now(UTC).isoformat()
                    }, exclude={session_id})
                    
                    yield f"data: {json.dumps({'type': 'connected', 'session_id': session_id})}\n\n"
                    yield f"data: {json.dumps({'type': 'endpoint', 'data': '/mcp/messages'})}\n\n"
                    
                    while True:
                        session = self.sessions.get(session_id)
                        if not session or session["status"] != "connected":
                            logger.info(f"Session {session_id} disconnected")
                            break

                        while session["messages"]:
                            message = session["messages"].pop(0)
                            yield f"data: {json.dumps(message)}\n\n"

                        yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now(UTC).isoformat()})}\n\n"
                        session["last_heartbeat"] = datetime.now(UTC)
                        await asyncio.sleep(self.config.heartbeat_interval)
                        
                except Exception as e:
                    logger.error(f"Error in SSE connection: {str(e)}")
                    if session_id in self.sessions:
                        self.sessions[session_id]["status"] = "disconnected"
                    raise
                finally:
                    if session_id in self.sessions:
                        self.sessions[session_id]["status"] = "disconnected"
                        logger.info(f"Session {session_id} cleaned up")

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
                tool = data.get("tool")
                args = data.get("args", {})

                if not session_id:
                    raise HTTPException(status_code=400, detail="Session ID is required")

                if session_id not in self.sessions:
                    raise HTTPException(status_code=404, detail="Session not found")

                session = self.sessions[session_id]
                if session["status"] != "connected":
                    raise HTTPException(status_code=400, detail="Session is not active")

                background_tasks.add_task(self.process_tool_request, session_id, tool, args)
                return JSONResponse({"status": "accepted"})

            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))

    async def process_tool_request(self, session_id: str, tool: str, args: Dict[str, Any]):
        try:
            session = self.sessions.get(session_id)
            if not session:
                logger.warning(f"Session {session_id} not found during tool processing")
                return

            if tool == "schedule_task":
                try:
                    task = Task(
                        name=args["name"],
                        schedule=args["schedule"],
                        type=TaskType(args["type"]),
                        command=args.get("command"),
                        api_url=args.get("api_url"),
                        api_method=args.get("api_method"),
                        api_headers=args.get("api_headers"),
                        api_body=args.get("api_body"),
                        prompt=args.get("prompt"),
                        reminder_message=args.get("reminder_message"),
                        reminder_title=args.get("reminder_title"),
                        do_only_once=args.get("do_only_once", True),
                        enabled=args.get("enabled", True)
                    )

                    task = await self.scheduler.add_task(task)
                    self.broadcast_message({
                        "type": "task_scheduled",
                        "task_id": task.id,
                        "task_name": task.name,
                        "schedule": task.schedule,
                        "type": task.type.value,
                        "status": task.status.value,
                        "next_run": task.next_run.isoformat() if task.next_run else None,
                        "timestamp": datetime.now(UTC).isoformat()
                    })
                except ValueError as e:
                    session["messages"].append({
                        "type": "error",
                        "error": f"Invalid task parameters: {str(e)}",
                        "timestamp": datetime.now(UTC).isoformat()
                    })

            elif tool == "list_tasks":
                try:
                    status_filter = args.get("status", "all")
                    type_filter = args.get("type", "all")
                    tasks = await self.scheduler.get_all_tasks()
                    
                    filtered_tasks = [
                        task.to_dict()
                        for task in tasks
                        if (status_filter == "all" or task.status.value == status_filter) and
                           (type_filter == "all" or task.type.value == type_filter)
                    ]

                    session["messages"].append({
                        "type": "task_list",
                        "tasks": filtered_tasks,
                        "timestamp": datetime.now(UTC).isoformat()
                    })
                except Exception as e:
                    session["messages"].append({
                        "type": "error",
                        "error": f"Error listing tasks: {str(e)}",
                        "timestamp": datetime.now(UTC).isoformat()
                    })

            elif tool == "run_task":
                try:
                    task_id = args["task_id"]
                    task = await self.scheduler.get_task(task_id)
                    
                    if not task:
                        session["messages"].append({
                            "type": "error",
                            "error": f"Task {task_id} not found",
                            "timestamp": datetime.now(UTC).isoformat()
                        })
                        return

                    if task.type == TaskType.AI:
                        # Para tareas de IA, notificamos al cliente para que las ejecute
                        request_time = datetime.now(UTC)
                        self.pending_ai_tasks[task_id] = {
                            "request_time": request_time,
                            "prompt": task.prompt
                        }
                        
                        self.broadcast_message({
                            "type": "ai_task_request",
                            "task_id": task_id,
                            "prompt": task.prompt,
                            "timestamp": request_time.isoformat()
                        })
                    else:
                        # Para otros tipos de tareas, las ejecutamos en el servidor
                        execution = await self.scheduler.run_task_now(task_id)
                        if execution:
                            self.broadcast_message({
                                "type": "task_started",
                                "task_id": task_id,
                                "execution_id": execution.id,
                                "start_time": execution.start_time.isoformat(),
                                "timestamp": datetime.now(UTC).isoformat()
                            })
                        else:
                            session["messages"].append({
                                "type": "error",
                                "error": f"Could not run task {task_id}",
                                "timestamp": datetime.now(UTC).isoformat()
                            })
                except Exception as e:
                    session["messages"].append({
                        "type": "error",
                        "error": f"Error running task: {str(e)}",
                        "timestamp": datetime.now(UTC).isoformat()
                    })

            elif tool == "execute_ai_task":
                try:
                    task_id = args["task_id"]
                    prompt = args["prompt"]
                    result = args["result"]
                    
                    if task_id not in self.pending_ai_tasks:
                        session["messages"].append({
                            "type": "error",
                            "error": f"No pending AI task found for ID: {task_id}",
                            "timestamp": datetime.now(UTC).isoformat()
                        })
                        return
                    
                    # Guardamos el resultado de la tarea de IA
                    execution = TaskExecution(
                        task_id=task_id,
                        start_time=self.pending_ai_tasks[task_id]["request_time"],
                        end_time=datetime.now(UTC),
                        status=TaskStatus.COMPLETED,
                        output=result
                    )
                    self.database.save_execution(execution)
                    
                    # Limpiamos la tarea pendiente
                    self.pending_ai_tasks.pop(task_id)
                    
                    # Notificamos a todos los clientes
                    self.broadcast_message({
                        "type": "ai_task_completed",
                        "task_id": task_id,
                        "execution_id": execution.id,
                        "result": result,
                        "timestamp": datetime.now(UTC).isoformat()
                    })
                except Exception as e:
                    session["messages"].append({
                        "type": "error",
                        "error": f"Error executing AI task: {str(e)}",
                        "timestamp": datetime.now(UTC).isoformat()
                    })

            else:
                session["messages"].append({
                    "type": "error",
                    "error": f"Unknown tool: {tool}",
                    "timestamp": datetime.now(UTC).isoformat()
                })

        except Exception as e:
            logger.error(f"Error processing tool request: {str(e)}")
            if session_id in self.sessions:
                session = self.sessions[session_id]
                session["messages"].append({
                    "type": "error",
                    "error": str(e),
                    "timestamp": datetime.now(UTC).isoformat()
                })

    def run(self, host: str = None, port: int = None):
        host = host or self.config.server_address
        port = port or self.config.server_port
        
        logger.info(f"Starting {self.config.server_name} v{self.config.server_version}")
        logger.info(f"Server running at http://{host}:{port}")
        
        uvicorn.run(
            self.app,
            host=host,
            port=port,
            log_level=self.config.log_level.lower()
        )

if __name__ == "__main__":
    scheduler = McpScheduler()
    scheduler.run()
