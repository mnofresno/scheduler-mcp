"""
MCP server implementation for MCP Scheduler.
"""
import logging
import json
import asyncio
import uvicorn
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from fastapi import Request, FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .task import Task, TaskStatus, TaskType, TaskExecution
from .scheduler import Scheduler
from .config import Config
from .persistence import Database
from .executor import Executor

logger = logging.getLogger(__name__)

class McpScheduler:
    def __init__(self, database: Database, executor: Executor):
        self.config = Config()
        # Usar lifespan en vez de on_event
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            self.start_scheduler()
            self.start_session_cleanup()
            self.start_ai_task_cleanup()
            self.start_health_check()
            self.start_performance_monitoring()
            self.start_metrics_collection()
            self.start_error_recovery()
            yield
        self.app = FastAPI(
            title=self.config.server_name,
            version=self.config.server_version,
            lifespan=lifespan
        )
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.client_to_sessions: Dict[str, set] = {}  # client_request_id -> set of session_ids
        self.persistent_sessions: set = set()  # session_ids marcadas como persistentes
        self.database = database
        self.executor = executor
        self.scheduler = Scheduler(self.database, self.executor, on_task_executed=self.on_task_executed)
        self.pending_ai_tasks = {}  # Inicializar tareas IA pendientes
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
                    if not self.scheduler.active:
                        logger.warning("Scheduler is not running, attempting to restart")
                        await self.scheduler.start()

                    # Verificar conexiones de base de datos
                    # La base de datos SQLite se reconecta automáticamente
                    # No necesitamos verificar la conexión

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

                    # Monitorear uso de memoria (sin psutil)
                    # Comentamos esta funcionalidad por ahora
                    # import psutil
                    # process = psutil.Process()
                    # memory_info = process.memory_info()
                    # if memory_info.rss > 500 * 1024 * 1024:  # 500MB
                    #     logger.warning(f"High memory usage: {memory_info.rss / 1024 / 1024:.2f}MB")

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

                    # Recolectar métricas de ejecuciones (usando el método correcto)
                    # Solo obtenemos las primeras 1000 tareas y sus ejecuciones
                    executions = []
                    for task in tasks[:1000]:
                        task_executions = self.database.get_executions(task.id, limit=10)
                        executions.extend(task_executions)
                    
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
                    # Obtenemos todas las tareas y filtramos las fallidas
                    all_tasks = await self.scheduler.get_all_tasks()
                    failed_tasks = [task for task in all_tasks if task.status == TaskStatus.FAILED]
                    
                    for task in failed_tasks:
                        # Por ahora, solo loggeamos las tareas fallidas
                        # En el futuro se puede implementar reintentos automáticos
                        logger.warning(f"Found failed task {task.id}: {task.name}")

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
                        "description": "Schedule a task to be executed at a specific time. The 'schedule' field must be a structured JSON object. See the 'schedule' property for details and examples.",
                        "endpoint": "messages",
                        "method": "POST",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Name of the task."},
                                "schedule": {
                                    "type": "object",
                                    "description": "Structured schedule object. Use one of the following formats:",
                                    "oneOf": [
                                        {
                                            "description": "Relative schedule: run after a delay from now.",
                                            "properties": {
                                                "schedule_type": {"type": "string", "enum": ["relative"], "description": "Type of schedule: 'relative' for a delay from now."},
                                                "unit": {"type": "string", "enum": ["seconds", "minutes", "hours"], "description": "Unit of time for the delay."},
                                                "amount": {"type": "integer", "minimum": 1, "description": "Amount of time units to wait before running the task."}
                                            },
                                            "required": ["schedule_type", "unit", "amount"],
                                            "examples": [
                                                {"schedule_type": "relative", "unit": "minutes", "amount": 5}
                                            ]
                                        },
                                        {
                                            "description": "Absolute schedule: run at a specific date and time (ISO8601).",
                                            "properties": {
                                                "schedule_type": {"type": "string", "enum": ["absolute"], "description": "Type of schedule: 'absolute' for a specific date/time."},
                                                "datetime": {"type": "string", "format": "date-time", "description": "ISO8601 datetime string in the future (e.g., '2025-12-25T10:00:00Z')."}
                                            },
                                            "required": ["schedule_type", "datetime"],
                                            "examples": [
                                                {"schedule_type": "absolute", "datetime": "2025-12-25T10:00:00Z"}
                                            ]
                                        },
                                        {
                                            "description": "Recurrent schedule: run periodically using a cron expression.",
                                            "properties": {
                                                "schedule_type": {"type": "string", "enum": ["recurrent"], "description": "Type of schedule: 'recurrent' for periodic tasks."},
                                                "cron": {"type": "string", "description": "Cron expression (e.g., '0 9 * * 1' for every Monday at 9:00)."}
                                            },
                                            "required": ["schedule_type", "cron"],
                                            "examples": [
                                                {"schedule_type": "recurrent", "cron": "0 9 * * 1"}
                                            ]
                                        }
                                    ]
                                },
                                "type": {"type": "string", "enum": ["shell_command", "api_call", "ai", "reminder"], "description": "Type of task to schedule."},
                                "command": {"type": "string", "description": "Shell command to execute (for shell_command tasks)."},
                                "api_url": {"type": "string", "description": "API URL to call (for api_call tasks)."},
                                "api_method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"], "description": "HTTP method for API call."},
                                "api_headers": {"type": "object", "description": "Headers for API call."},
                                "api_body": {"type": "object", "description": "Body for API call."},
                                "prompt": {"type": "string", "description": "Prompt for AI tasks."},
                                "reminder_message": {"type": "string", "description": "Message to show for reminder tasks."},
                                "reminder_title": {"type": "string", "description": "Title for reminder tasks."},
                                "do_only_once": {"type": "boolean", "description": "If true, the task will only run once."},
                                "enabled": {"type": "boolean", "description": "If false, the task will not be scheduled until enabled."}
                            },
                            "required": ["name", "schedule", "type"],
                            "examples": [
                                {
                                    "name": "Drink water",
                                    "schedule": {"schedule_type": "relative", "unit": "minutes", "amount": 5},
                                    "type": "reminder",
                                    "reminder_message": "Es hora de tomar agua."
                                },
                                {
                                    "name": "Doctor appointment",
                                    "schedule": {"schedule_type": "absolute", "datetime": "2025-12-25T10:00:00Z"},
                                    "type": "reminder",
                                    "reminder_message": "Tienes turno con el doctor."
                                },
                                {
                                    "name": "Weekly report",
                                    "schedule": {"schedule_type": "recurrent", "cron": "0 9 * * 1"},
                                    "type": "reminder",
                                    "reminder_message": "Enviar reporte semanal."
                                }
                            ]
                        }
                    },
                    {
                        "name": "list_tasks",
                        "description": "List all scheduled tasks",
                        "endpoint": "messages",
                        "method": "POST",
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
                        "endpoint": "messages",
                        "method": "POST",
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
                        "endpoint": "messages",
                        "method": "POST",
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
        async def sse_endpoint(
            request: Request, 
            session_id: str = Query(None),
            request_id: str = Query(None),
            persistent: bool = Query(False)
        ):
            # Support both session_id and request_id parameters
            if not session_id and not request_id:
                raise HTTPException(status_code=400, detail="Session ID or Request ID is required")
            # Use request_id as session_id if session_id is not provided
            if not session_id and request_id:
                session_id = request_id

            logger.info(f"SSE endpoint requested for session {session_id} (persistent={persistent})")
            
            # Si ya existe una sesión, la actualizamos y la devolvemos para continuarla
            if session_id in self.sessions:
                logger.info(f"Session {session_id} already exists. Resuming connection.")
                self.sessions[session_id]["last_heartbeat"] = datetime.now(UTC)
                self.sessions[session_id]["status"] = "connected"
                self.sessions[session_id]["persistent"] = persistent
            else:
                logger.info(f"Creating new session: {session_id}")
                self.sessions[session_id] = {
                    "queue": asyncio.Queue(),
                    "last_heartbeat": datetime.now(UTC),
                    "status": "connected",
                    "messages": [],
                    "persistent": persistent,
                    "created_at": datetime.now(UTC)  # Added for session lifetime tracking
                }
                # Emitir un mensaje de conexión para la nueva sesión
                self.send_sse_message(session_id, {"type": "connected", "session_id": session_id})
                self.send_sse_message(session_id, {"type": "endpoint", "data": "/mcp/messages"})

            if persistent:
                self.persistent_sessions.add(session_id)

            # Si la sesión es persistente y se provee client_request_id, regístrala en el mapeo
            client_request_id = request.query_params.get("client_request_id")
            if persistent and client_request_id:
                if client_request_id not in self.client_to_sessions:
                    self.client_to_sessions[client_request_id] = set()
                self.client_to_sessions[client_request_id].add(session_id)
                logger.info(f"[SSE] Persistent session {session_id} registered for client_request_id {client_request_id}")

            async def event_generator():
                last_heartbeat_sent = datetime.now(UTC)
                try:
                    while True:
                        try:
                            # Verificar si la sesión sigue activa
                            if session_id not in self.sessions:
                                logger.info(f"[SSE-TRACE] Session {session_id} no longer exists. Exiting event_generator loop.")
                                break
                            # Enviar heartbeats cada self.config.heartbeat_interval segundos
                            now = datetime.now(UTC)
                            if (now - last_heartbeat_sent).total_seconds() > self.config.heartbeat_interval:
                                heartbeat_message = {"type": "heartbeat", "timestamp": now.isoformat()}
                                logger.debug(f"Sending heartbeat for session {session_id}")
                                yield f"data: {json.dumps(heartbeat_message)}\n\n"
                                last_heartbeat_sent = now

                            # Intentar obtener un mensaje de la cola con un timeout
                            msg = await asyncio.wait_for(self.sessions[session_id]["queue"].get(), timeout=1.0) # Espera 1 segundo
                            logger.info(f"[SSE-TRACE] Yielding message to client for session {session_id}: {msg}")
                            # Resetear el contador de inactividad de la sesión
                            self.sessions[session_id]["last_heartbeat"] = datetime.now(UTC)
                            logger.debug(f"Sending message to session {session_id}: {msg}")
                            yield f"data: {json.dumps(msg)}\n\n"
                        except asyncio.TimeoutError:
                            # No hay mensajes, continuar con el bucle para el heartbeat
                            pass
                        except Exception as e:
                            logger.error(f"Error in event_generator for session {session_id}: {e}")
                            # Si la sesión ya no existe, salir del bucle
                            if session_id not in self.sessions:
                                logger.info(f"Session {session_id} was removed after error. Exiting event_generator loop.")
                                break
                            await asyncio.sleep(1) # Esperar un poco antes de reintentar para evitar spam de errores
                finally:
                    logger.info(f"[SSE-TRACE] SSE event generator for session {session_id} finished or client disconnected. Cleaning up session.")
                    self.cleanup_session(session_id)

            return StreamingResponse(event_generator(), media_type="text/event-stream")

        @self.app.post("/mcp/messages")
        async def process_message(request: Request, background_tasks: BackgroundTasks):
            logger.info("=== ENDPOINT CALLED: /mcp/messages ===")
            try:
                logger.info("Received POST request to /mcp/messages")
                raw_body = await request.body()
                logger.info(f"Raw request body: {raw_body}")
                try:
                    data = await request.json()
                except Exception as e:
                    logger.error(f"Error parsing JSON: {e}")
                    raise HTTPException(status_code=400, detail="Invalid JSON")
                logger.info(f"Parsed request data: {data}")
                
                # Manejar formato JSON-RPC
                if "jsonrpc" in data:
                    session_id = data.get("id")
                    tool = data.get("method")
                    args = data.get("params", {})
                    client_request_id = data.get("client_request_id")
                else:
                    session_id = data.get("session_id")
                    tool = data.get("tool")
                    args = data.get("args", {})
                    client_request_id = data.get("client_request_id")

                logger.info(f"Extracted: session_id={session_id}, tool={tool}, args={args}")

                if not session_id:
                    logger.error("Session ID is required but not provided")
                    raise HTTPException(status_code=400, detail="Session ID is required")

                if session_id not in self.sessions:
                    logger.error(f"Session {session_id} not found. Available sessions: {list(self.sessions.keys())}")
                    raise HTTPException(status_code=404, detail="Session not found")

                session = self.sessions[session_id]
                logger.info("Session found: {}, status: {}".format(session_id, session["status"]))
                
                if session["status"] != "connected":
                    logger.error(f"Session {session_id} is not active, status: {session['status']}")
                    raise HTTPException(status_code=400, detail="Session is not active")

                logger.info(f"Adding background task: process_tool_request({session_id}, {tool}, {args})")
                background_tasks.add_task(self.process_tool_request, session_id, tool, args, client_request_id)
                logger.info("Background task added successfully")
                
                # Agregar un log de confirmación inmediato
                logger.info(f"Returning response for session {session_id}")
                return JSONResponse({"status": "accepted"})

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {str(e)}")
                raise HTTPException(status_code=400, detail="Invalid JSON")
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/debug/sessions")
        async def debug_sessions():
            # Devuelve el estado actual de todas las sesiones (para debugging/testing)
            return {
                "sessions": {
                    sid: {
                        "status": s["status"],
                        "persistent": s.get("persistent", False),
                        "last_heartbeat": s["last_heartbeat"].isoformat() if s.get("last_heartbeat") else None,
                        "created_at": s.get("created_at").isoformat() if s.get("created_at") else None,
                        "messages_in_queue": s["queue"].qsize() if "queue" in s else 0
                    }
                    for sid, s in self.sessions.items()
                }
            }

    async def process_tool_request(self, session_id: str, tool: str, args: Dict[str, Any], client_request_id: Optional[str] = None):
        logger.info(f"=== BACKGROUND TASK STARTED: process_tool_request({session_id}, {tool}) ===")
        try:
            logger.info(f"Processing tool request: session_id={session_id}, tool={tool}, args={args}")

            session_info = self.sessions.get(session_id)
            if not session_info or session_info["status"] != "connected":
                logger.error(f"Session not found or not connected: {session_id}")
                self.send_sse_message(session_id, {"type": "error", "error": "Session not connected"})
                return

            logger.info(f"Session found: {session_id}, status: {session_info['status']}")

            # Aquí se manejan los diferentes tipos de herramientas
            if tool == "schedule_task":
                # Create a new task
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
                    do_only_once=True,  # Los reminders deben ejecutarse solo una vez
                    client_request_id=client_request_id # Pass client_request_id to Task
                )
                logger.info(f"Creating task with args: {args}")

                task_id = await self.scheduler.add_task(task)

                # Determine next run time for display purposes in result message
                next_run_time = await self.scheduler.get_next_run_time(task)

                message_content = f"Recordatorio '{task.name}' programado exitosamente para {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}" 

                # Send result message
                result_message = {
                    "type": "result",
                    "result": {
                        "task_id": task_id, 
                        "task_name": task.name,
                        "schedule": task.schedule,
                        "type": task.type.value,
                        "status": "pending",
                        "next_run": next_run_time.isoformat(), 
                        "message": message_content
                    },
                    "timestamp": datetime.now(UTC).isoformat(),
                    "client_request_id": client_request_id # Include client_request_id here
                }
                self.send_sse_message(session_id, result_message) # Send to specific session_id
                logger.info(f"Sent result message: {result_message}")

                # Guardar el mapeo client_request_id -> set de session_ids
                if client_request_id:
                    # Inicializar el set si no existe
                    if client_request_id not in self.client_to_sessions:
                        self.client_to_sessions[client_request_id] = set()
                    # Si la sesión es persistente, asegúrate de que esté en el set y priorízala
                    if session_info.get("persistent"):
                        self.client_to_sessions[client_request_id].add(session_id)
                    else:
                        # Solo agrega sesiones temporales si no hay ninguna persistente
                        persistent_sessions = [sid for sid in self.client_to_sessions[client_request_id] if self.sessions.get(sid, {}).get("persistent")]
                        if not persistent_sessions:
                            self.client_to_sessions[client_request_id].add(session_id)
                        # Si ya hay una persistente, no agregues la temporal

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

                    session_info["messages"].append({
                        "type": "task_list",
                        "tasks": filtered_tasks,
                        "timestamp": datetime.now(UTC).isoformat()
                    })
                except Exception as e:
                    session_info["messages"].append({
                        "type": "error",
                        "error": f"Error listing tasks: {str(e)}",
                        "timestamp": datetime.now(UTC).isoformat()
                    })

            elif tool == "run_task":
                try:
                    task_id = args["task_id"]
                    task = await self.scheduler.get_task(task_id)
                    
                    if not task:
                        session_info["messages"].append({
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
                            session_info["messages"].append({
                                "type": "error",
                                "error": f"Could not run task {task_id}",
                                "timestamp": datetime.now(UTC).isoformat()
                            })
                except Exception as e:
                    session_info["messages"].append({
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
                        session_info["messages"].append({
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
                    session_info["messages"].append({
                        "type": "error",
                        "error": f"Error executing AI task: {str(e)}",
                        "timestamp": datetime.now(UTC).isoformat()
                    })

            else:
                session_info["messages"].append({
                    "type": "error",
                    "error": f"Unknown tool: {tool}",
                    "timestamp": datetime.now(UTC).isoformat()
                })

        except Exception as e:
            logger.error(f"Error processing tool request: {str(e)}")
            if session_id in self.sessions:
                session_info = self.sessions[session_id]
                session_info["messages"].append({
                    "type": "error",
                    "error": str(e),
                    "timestamp": datetime.now(UTC).isoformat()
                })

    def on_task_executed(self, task, execution):
        logger.info(f"[on_task_executed] Callback called for task {task.id} ({task.name}), type={task.type}, status={execution.status}")
        # Emitir mensaje SSE de tipo 'reminder' si es un recordatorio ejecutado exitosamente
        if task.type == TaskType.REMINDER and execution.status == TaskStatus.COMPLETED:
            reminder_message = {
                "type": "reminder",
                "task_id": task.id,
                "task_name": task.name,
                "message": task.reminder_message,
                "executed_at": execution.end_time.isoformat() if execution.end_time else None,
                "timestamp": datetime.now(UTC).isoformat(),
                "client_request_id": task.client_request_id
            }
            # Log de todas las sesiones activas y persistentes
            active_persistent_sessions = [sid for sid, sess in self.sessions.items() if sess.get("persistent") and sess.get("status") == "connected"]
            logger.info(f"[on_task_executed] Sesiones activas y persistentes: {active_persistent_sessions}")
            logger.info(f"[on_task_executed] Estado de todas las sesiones al ejecutar recordatorio: {{sid: {{'status': sess.get('status'), 'persistent': sess.get('persistent'), 'created_at': str(sess.get('created_at')), 'last_heartbeat': str(sess.get('last_heartbeat'))}} for sid, sess in self.sessions.items()}}")
            # Buscar sesiones persistentes primero
            session_ids = self.client_to_sessions.get(task.client_request_id, set())
            logger.info(f"[on_task_executed] client_to_sessions for {task.client_request_id}: {session_ids}")
            persistent = [sid for sid in session_ids if self.sessions.get(sid, {}).get("persistent") and self.sessions.get(sid, {}).get("status") == "connected"]
            logger.info(f"[on_task_executed] persistent target_sessions: {persistent}")
            target_sessions = persistent if persistent else [sid for sid in session_ids if self.sessions.get(sid, {}).get("status") == "connected"]
            logger.info(f"[on_task_executed] final target_sessions: {target_sessions}")
            if target_sessions:
                for sid in target_sessions:
                    logger.info(f"[on_task_executed] Sending reminder to session {sid}")
                    self.send_sse_message(sid, reminder_message)
            else:
                # Enviar a todas las sesiones activas y persistentes (igual que heartbeat)
                global_sessions = active_persistent_sessions
                if global_sessions:
                    logger.info(f"[on_task_executed] No session for client_request_id {task.client_request_id}. Sending reminder to all persistent sessions: {global_sessions}")
                    for sid in global_sessions:
                        self.send_sse_message(sid, reminder_message)
                else:
                    logger.warning(f"[on_task_executed] No active session found for client_request_id {task.client_request_id} nor any persistent session. Not sending reminder via SSE.")
        # TODO: This should ideally only be sent if the original request expects a final result.
        # Currently, it's broadcasting, which might not be desired.
        result_message = {
            "type": "result",
            "result": {
                "task_id": task.id,
                "task_name": task.name,
                "status": execution.status.value,
                "output": execution.output,
                "type": task.type.value,
                "executed_at": execution.end_time.isoformat() if execution.end_time else None
            },
            "timestamp": datetime.now(UTC).isoformat(),
            "client_request_id": task.client_request_id
        }
        session_ids = self.client_to_sessions.get(task.client_request_id, set())
        # Limpiar sesiones inactivas del set antes de enviar
        session_ids = set([sid for sid in session_ids if self.sessions.get(sid, {}).get("status") == "connected"])
        self.client_to_sessions[task.client_request_id] = session_ids
        persistent = [sid for sid in session_ids if self.sessions.get(sid, {}).get("persistent")]
        target_sessions = persistent if persistent else list(session_ids)
        if target_sessions:
            for sid in target_sessions:
                self.send_sse_message(sid, result_message)
        else:
            logger.warning(f"[on_task_executed] No active session found for client_request_id {task.client_request_id}. Not sending result via SSE.")

    def _make_json_serializable(self, obj):
        # Convierte objetos Task, Execution, datetime, etc. a tipos serializables
        import datetime
        from .task import Task, TaskExecution
        if isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(v) for v in obj]
        elif hasattr(obj, 'dict') and callable(getattr(obj, 'dict', None)):
            return self._make_json_serializable(obj.dict())
        elif hasattr(obj, '__dict__'):
            return self._make_json_serializable(vars(obj))
        elif isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        else:
            return str(obj)

    def send_sse_message(self, session_id: str, message: Dict[str, Any]):
        session = self.sessions.get(session_id)
        if session and session["status"] == "connected":
            try:
                serializable_message = self._make_json_serializable(message)
                logger.info(f"[SSE-TRACE] Putting message to queue for session {session_id}: {serializable_message}")
                session["queue"].put_nowait(serializable_message)
                logger.info(f"Message put to queue for session {session_id}: {serializable_message}")
            except asyncio.QueueFull: # Si la cola está llena, el cliente no está leyendo lo suficientemente rápido
                logger.warning(f"SSE queue full for session {session_id}. Dropping message: {message}")
            except Exception as e:
                logger.error(f"Error putting message to SSE queue for session {session_id}: {e}. Message: {message}")
        else:
            logger.warning(f"Session {session_id} not active. Not sending message: {message}")

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

    def cleanup_session(self, session_id: str):
        """Remove a session and notify others."""
        if session_id in self.sessions:
            logger.info(f"Cleaning up session: {session_id}")
            now = datetime.now(UTC)
            self.broadcast_message({
                "type": "session_disconnected",
                "session_id": session_id,
                "timestamp": now.isoformat()
            }, exclude={session_id})
            del self.sessions[session_id]
        else:
            logger.info(f"Session {session_id} already cleaned up or does not exist.")

if __name__ == "__main__":
    scheduler = McpScheduler()
    scheduler.run()
