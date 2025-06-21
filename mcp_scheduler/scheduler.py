"""
Task scheduler implementation for MCP Scheduler.
"""
import asyncio
import logging
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional

import croniter

from .task import Task, TaskStatus, TaskExecution
from .persistence import Database
from .executor import Executor
from .utils import parse_relative_time_to_cron, parse_structured_schedule

logger = logging.getLogger(__name__)


class Scheduler:
    """Task scheduler to manage cron-based task execution."""
    
    def __init__(self, database: Database, executor: Executor, on_task_executed=None):
        """Initialize the task scheduler."""
        self.database = database
        self.executor = executor
        self.active = False
        self._check_interval = 5  # seconds
        self._scheduler_task: Optional[asyncio.Task] = None
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self.on_task_executed = on_task_executed
    
    async def start(self):
        """Start the scheduler."""
        if self.active:
            logger.warning("Scheduler is already running")
            return
            
        logger.info("Starting scheduler")
        self.active = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
    async def stop(self):
        """Stop the scheduler."""
        if not self.active:
            logger.warning("Scheduler is not running")
            return
            
        logger.info("Stopping scheduler")
        self.active = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
            
        # Cancel any running tasks
        running_tasks = list(self._running_tasks.items())
        for task_id, task in running_tasks:
            logger.info(f"Cancelling running task: {task_id}")
            task.cancel()
    
    async def _scheduler_loop(self):
        """Main scheduler loop to check for tasks to run."""
        logger.info("[Scheduler] Starting scheduler loop")
        try:
            while self.active:
                logger.debug("[Scheduler] Loop iteration - checking tasks")
                await self._check_tasks()
                logger.debug(f"[Scheduler] Sleeping for {self._check_interval} seconds")
                await asyncio.sleep(self._check_interval)
        except asyncio.CancelledError:
            logger.info("Scheduler loop cancelled")
            raise
        except Exception:
            logger.exception("Error in scheduler loop")
            self.active = False
            raise
    
    async def _check_tasks(self):
        """Check for tasks that need to be executed."""
        try:
            tasks = self.database.get_all_tasks()
            now = datetime.now(UTC)
            logger.debug(f"[Scheduler] Checking {len(tasks)} tasks at {now}")
            
            for task in tasks:
                if not task.enabled:
                    logger.debug(f"[Scheduler] Skipping disabled task {task.id} ({task.name})")
                    continue
                if task.id in self._running_tasks:
                    logger.debug(f"[Scheduler] Skipping running task {task.id} ({task.name})")
                    continue

                # --- NUEVA LÓGICA: schedule estructurado ---
                try:
                    schedule_str = parse_structured_schedule(task.schedule)
                except Exception as e:
                    logger.error(f"Invalid structured schedule for task {task.id}: {e}")
                    continue

                if schedule_str and isinstance(schedule_str, str) and schedule_str.startswith('delay:'):
                    if task.next_run is None:
                        delay_seconds = int(schedule_str.split(':')[1])
                        task.next_run = now + timedelta(seconds=delay_seconds)
                        self.database.save_task(task)
                        logger.info(f"[Scheduler] Calculated next_run (delay) for task {task.id}: {task.next_run}")
                    logger.debug(f"[Scheduler] Task {task.id} ({task.name}) - next_run: {task.next_run}, now: {now}")
                    if task.next_run and task.next_run <= now:
                        logger.info(f"[Scheduler] Starting execution of task {task.id} ({task.name}) [delay mode]")
                        self._running_tasks[task.id] = asyncio.create_task(
                            self._execute_task(task)
                        )
                    else:
                        logger.debug(f"[Scheduler] Task {task.id} not ready yet - next_run: {task.next_run}")
                    continue
                # --- FIN NUEVA LÓGICA ---

                # Lógica para cron
                if task.next_run is None:
                    try:
                        cron = croniter.croniter(schedule_str, now)
                        task.next_run = cron.get_next(datetime)
                        self.database.save_task(task)
                        logger.info(f"[Scheduler] Calculated next_run for task {task.id}: {task.next_run}")
                    except Exception as e:
                        logger.error(f"Invalid cron expression for task {task.id}: {e}")
                        continue
                logger.debug(f"[Scheduler] Task {task.id} ({task.name}) - next_run: {task.next_run}, now: {now}")
                if task.next_run and task.next_run <= now:
                    logger.info(f"[Scheduler] Starting execution of task {task.id} ({task.name})")
                    self._running_tasks[task.id] = asyncio.create_task(
                        self._execute_task(task)
                    )
                else:
                    logger.debug(f"[Scheduler] Task {task.id} not ready yet - next_run: {task.next_run}")
        except Exception:
            logger.exception("Error checking tasks")

    async def _execute_task(self, task: Task):
        """Execute a task and update its status."""
        logger.info(f"Starting task execution: {task.id} ({task.name})")
        execution = None
        try:
            task.status = TaskStatus.RUNNING
            task.last_run = datetime.now(UTC)
            self.database.save_task(task)
            execution = await self.executor.execute_task(task)
            self.database.save_execution(execution)
            if self.on_task_executed:
                try:
                    logger.info(f"[Scheduler] Calling on_task_executed callback for task {task.id} ({task.name})")
                    await asyncio.to_thread(self.on_task_executed, task, execution)
                    logger.info(f"[Scheduler] Callback on_task_executed completed for task {task.id} ({task.name})")
                except Exception as e:
                    logger.error(f"Error in on_task_executed callback: {e}")
            if task.do_only_once and execution.status == TaskStatus.COMPLETED:
                logger.info(f"One-off task {task.id} completed successfully, disabling it")
                task.enabled = False
                task.status = TaskStatus.DISABLED
                task.next_run = None
                self.database.save_task(task)
            else:
                try:
                    schedule_str = parse_structured_schedule(task.schedule)
                    now = datetime.now(UTC)
                    if schedule_str and schedule_str.startswith('delay:'):
                        logger.info(f"Task {task.id} used delay:N schedule, not rescheduling.")
                        task.next_run = None
                    else:
                        cron = croniter.croniter(schedule_str, now)
                        task.next_run = cron.get_next(datetime)
                except Exception as e:
                    logger.error(f"Failed to calculate next_run for task {task.id}: {e}")
                    task.next_run = None
                task.status = execution.status
                self.database.save_task(task)
            logger.info(f"Task execution completed: {task.id} - Status: {execution.status.value}")
        except Exception as e:
            logger.exception(f"Error executing task {task.id}")
            task.status = TaskStatus.FAILED
            self.database.save_task(task)
            execution = TaskExecution(
                task_id=task.id,
                start_time=task.last_run or datetime.now(UTC),
                end_time=datetime.now(UTC),
                status=TaskStatus.FAILED,
                error=str(e)
            )
            self.database.save_execution(execution)
        finally:
            if task.id in self._running_tasks:
                del self._running_tasks[task.id]

    async def get_next_run_time(self, task: Task) -> Optional[datetime]:
        """Calculate the next run time for a given task."""
        if not task.schedule:
            return None
        now = datetime.now(UTC)
        try:
            schedule_str = parse_structured_schedule(task.schedule)
            if schedule_str.startswith('delay:'):
                delay_seconds = int(schedule_str.split(':')[1])
                return now + timedelta(seconds=delay_seconds)
            cron = croniter.croniter(schedule_str, now)
            return cron.get_next(datetime)
        except Exception as e:
            logger.error(f"Invalid schedule for task {task.id}: {e}")
            return None

    async def add_task(self, task: Task) -> Task:
        """Add a new task to the scheduler."""
        logger.info(f"=== ADD_TASK CALLED: schedule='{task.schedule}' ===")
        now = datetime.now(UTC)
        try:
            schedule_str = parse_structured_schedule(task.schedule)
            if schedule_str.startswith('delay:'):
                delay_seconds = int(schedule_str.split(':')[1])
                task.next_run = now + timedelta(seconds=delay_seconds)
            else:
                cron = croniter.croniter(schedule_str, now)
                task.next_run = cron.get_next(datetime)
        except Exception as e:
            logger.error(f"Could not parse structured schedule: {e}")
            task.next_run = now + timedelta(seconds=10)
        self.database.save_task(task)
        logger.info(f"Added new task: {task.id} ({task.name})")
        return task

    async def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        """Update an existing task."""
        task = self.database.get_task(task_id)
        if not task:
            return None
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        if "schedule" in kwargs:
            try:
                schedule_str = parse_structured_schedule(task.schedule)
                now = datetime.now(UTC)
                if schedule_str.startswith('delay:'):
                    delay_seconds = int(schedule_str.split(':')[1])
                    task.next_run = now + timedelta(seconds=delay_seconds)
                else:
                    cron = croniter.croniter(schedule_str, now)
                    task.next_run = cron.get_next(datetime)
            except Exception as e:
                logger.error(f"Could not parse structured schedule: {e}")
                task.next_run = now + timedelta(seconds=10)
        task.updated_at = datetime.now(UTC)
        self.database.save_task(task)
        logger.info(f"Updated task: {task.id} ({task.name})")
        return task
    
    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        # Cancel the task if it's running
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]
        
        result = self.database.delete_task(task_id)
        if result:
            logger.info(f"Deleted task: {task_id}")
        
        return result
    
    async def enable_task(self, task_id: str) -> Optional[Task]:
        """Enable a task."""
        return await self.update_task(task_id, enabled=True, status=TaskStatus.PENDING)
    
    async def disable_task(self, task_id: str) -> Optional[Task]:
        """Disable a task."""
        return await self.update_task(task_id, enabled=False, status=TaskStatus.DISABLED)
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self.database.get_task(task_id)
    
    async def get_all_tasks(self) -> List[Task]:
        """Get all tasks."""
        return self.database.get_all_tasks()
    
    async def get_task_executions(self, task_id: str, limit: int = 10) -> List[TaskExecution]:
        """Get executions for a task."""
        return self.database.get_executions(task_id, limit)
    
    async def run_task_now(self, task_id: str) -> Optional[TaskExecution]:
        """Run a task immediately outside its schedule."""
        task = self.database.get_task(task_id)
        if not task:
            return None
        
        # Skip if the task is already running
        if task_id in self._running_tasks:
            logger.warning(f"Task {task_id} is already running")
            return None
        
        # Execute the task
        task.status = TaskStatus.RUNNING
        task.last_run = datetime.now(UTC)
        self.database.save_task(task)
        
        execution = await self.executor.execute_task(task)
        self.database.save_execution(execution)
        
        # If this is a do_only_once task and it completed successfully, disable it
        if task.do_only_once and execution.status == TaskStatus.COMPLETED:
            logger.info(f"One-off task {task.id} run manually and completed, disabling it")
            task.enabled = False
            task.status = TaskStatus.DISABLED
        else:
            # Update task status for recurring tasks or failed one-off tasks
            task.status = execution.status
            
        self.database.save_task(task)
        
        return execution