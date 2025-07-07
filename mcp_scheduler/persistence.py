"""
SQLite persistence layer for MCP Scheduler.
"""
import json
import sqlite3
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
import os
import sys

from .task import Task, TaskExecution, TaskStatus, TaskType
from .dbcreator import ensure_db

logger = logging.getLogger(__name__)


class Database:
    """SQLite database for task persistence."""
    
    def __init__(self, db_path="scheduler.db"):
        """Initialize the database connection."""
        self.db_path = db_path
        ensure_db()  # Ensure DB and tables exist before anything else
        self._create_tables()
    
    def _create_tables(self):
        """Create the necessary tables if they don't exist."""
        logger.info(f"Attempting to create database tables at {self.db_path}")
        # Ensure the directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        # Connect to the database. If it doesn't exist, it will be created.
        with sqlite3.connect(self.db_path) as conn:
            logger.debug("Database connection opened.")
            # Check if we need to add reminder columns
            try:
                logger.debug("Executing: SELECT reminder_title, reminder_message, client_request_id FROM tasks LIMIT 1")
                cursor = conn.execute("SELECT reminder_title, reminder_message, client_request_id FROM tasks LIMIT 1")
                has_reminder_columns = True
                has_client_request_id = True
                logger.info("Tasks table already has reminder columns and client_request_id.")
            except sqlite3.OperationalError as e:
                logger.warning(f"Error checking for reminder/client_request_id columns: {e}")
                has_reminder_columns = False
                has_client_request_id = False
                logger.info("Tasks table does not have reminder columns or client_request_id yet, or tasks table does not exist.")
            
            # Create tasks table if it doesn't exist
            logger.debug("Executing CREATE TABLE IF NOT EXISTS tasks...")
            conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                schedule TEXT NOT NULL,
                type TEXT NOT NULL,
                command TEXT,
                api_url TEXT,
                api_method TEXT,
                api_headers TEXT,
                api_body TEXT,
                prompt TEXT,
                description TEXT,
                enabled INTEGER NOT NULL,
                do_only_once INTEGER NOT NULL,
                last_run TEXT,
                next_run TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reminder_title TEXT,
                reminder_message TEXT,
                client_request_id TEXT
            )
            """)
            logger.info("Attempted to create tasks table.")
            
            # Add reminder columns if they don't exist
            if not has_reminder_columns:
                try:
                    logger.debug("Executing ALTER TABLE tasks ADD COLUMN reminder_title...")
                    conn.execute("ALTER TABLE tasks ADD COLUMN reminder_title TEXT")
                    logger.debug("Executing ALTER TABLE tasks ADD COLUMN reminder_message...")
                    conn.execute("ALTER TABLE tasks ADD COLUMN reminder_message TEXT")
                    logger.info("Added reminder columns to tasks table")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Reminder columns already exist or error adding them: {e}")
            # Add client_request_id column if it doesn't exist
            if not has_client_request_id:
                try:
                    logger.debug("Executing ALTER TABLE tasks ADD COLUMN client_request_id...")
                    conn.execute("ALTER TABLE tasks ADD COLUMN client_request_id TEXT")
                    logger.info("Added client_request_id column to tasks table")
                except sqlite3.OperationalError as e:
                    logger.warning(f"client_request_id column already exists or error adding it: {e}")
            
            logger.debug("Executing CREATE TABLE IF NOT EXISTS executions...")
            conn.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                status TEXT NOT NULL,
                output TEXT,
                error TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (id)
            )
            """)
            logger.info("Attempted to create executions table.")
            
            conn.commit()
            logger.info("Database table creation committed.")
        logger.debug("Database connection closed.")
    
    def save_task(self, task: Task) -> None:
        """Save a task to the database."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            # Check if reminder columns exist
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tasks
                    (id, name, schedule, type, command, api_url, api_method, api_headers, 
                     api_body, prompt, description, enabled, do_only_once, last_run, next_run, 
                     status, created_at, updated_at, reminder_title, reminder_message, client_request_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.id,
                        task.name,
                        task.schedule,
                        task.type.value,
                        task.command,
                        task.api_url,
                        task.api_method,
                        json.dumps(task.api_headers) if task.api_headers else None,
                        json.dumps(task.api_body) if task.api_body else None,
                        task.prompt,
                        task.description,
                        1 if task.enabled else 0,
                        1 if task.do_only_once else 0,
                        task.last_run.isoformat() if task.last_run else None,
                        task.next_run.isoformat() if task.next_run else None,
                        task.status.value,
                        task.created_at.isoformat(),
                        task.updated_at.isoformat(),
                        task.reminder_title,
                        task.reminder_message,
                        task.client_request_id
                    )
                )
            except sqlite3.OperationalError:
                # Fallback for databases without reminder columns
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tasks
                    (id, name, schedule, type, command, api_url, api_method, api_headers, 
                     api_body, prompt, description, enabled, do_only_once, last_run, next_run, 
                     status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.id,
                        task.name,
                        task.schedule,
                        task.type.value,
                        task.command,
                        task.api_url,
                        task.api_method,
                        json.dumps(task.api_headers) if task.api_headers else None,
                        json.dumps(task.api_body) if task.api_body else None,
                        task.prompt,
                        task.description,
                        1 if task.enabled else 0,
                        1 if task.do_only_once else 0,
                        task.last_run.isoformat() if task.last_run else None,
                        task.next_run.isoformat() if task.next_run else None,
                        task.status.value,
                        task.created_at.isoformat(),
                        task.updated_at.isoformat()
                    )
                )
                
                # Log warning about missing reminder columns
                logger.warning("Database missing reminder columns - task reminder data not saved")
                
            conn.commit()
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return self._row_to_task(row)
    
    def get_all_tasks(self) -> List[Task]:
        """Get all tasks."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM tasks")
            rows = cursor.fetchall()
            
            return [self._row_to_task(row) for row in rows]
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            
            return cursor.rowcount > 0
    
    def save_execution(self, execution: TaskExecution) -> None:
        """Save a task execution to the database."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            if execution.id is None:
                conn.execute(
                    """
                    INSERT INTO executions
                    (task_id, start_time, end_time, status, output, error)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        execution.task_id,
                        execution.start_time.isoformat(),
                        execution.end_time.isoformat() if execution.end_time else None,
                        execution.status.value,
                        execution.output,
                        execution.error
                    )
                )
            else:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO executions
                    (id, task_id, start_time, end_time, status, output, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        execution.id,
                        execution.task_id,
                        execution.start_time.isoformat(),
                        execution.end_time.isoformat() if execution.end_time else None,
                        execution.status.value,
                        execution.output,
                        execution.error
                    )
                )
            conn.commit()
    
    def get_executions(self, task_id: str, limit: int = 10) -> List[TaskExecution]:
        """Get executions for a task."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM executions WHERE task_id = ? ORDER BY start_time DESC LIMIT ?", 
                (task_id, limit)
            )
            rows = cursor.fetchall()
            
            return [self._row_to_execution(row) for row in rows]
    
    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """Convert a database row to a Task object."""
        # Check for reminder fields in the row
        has_reminder_fields = "reminder_title" in row.keys() and "reminder_message" in row.keys()
        has_client_request_id = "client_request_id" in row.keys()
        task = Task(
            id=row["id"],
            name=row["name"],
            schedule=row["schedule"],
            type=TaskType(row["type"]),
            command=row["command"],
            api_url=row["api_url"],
            api_method=row["api_method"],
            api_headers=json.loads(row["api_headers"]) if row["api_headers"] else None,
            api_body=json.loads(row["api_body"]) if row["api_body"] else None,
            prompt=row["prompt"],
            description=row["description"],
            enabled=bool(row["enabled"]),
            do_only_once=bool(row["do_only_once"]),
            last_run=datetime.fromisoformat(row["last_run"]) if row["last_run"] else None,
            next_run=datetime.fromisoformat(row["next_run"]) if row["next_run"] else None,
            status=TaskStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            reminder_title=row["reminder_title"] if has_reminder_fields else None,
            reminder_message=row["reminder_message"] if has_reminder_fields else None,
            client_request_id=row["client_request_id"] if has_client_request_id else None
        )
        return task
    
    def _row_to_execution(self, row: sqlite3.Row) -> TaskExecution:
        """Convert a database row to a TaskExecution object."""
        return TaskExecution(
            id=row["id"],
            task_id=row["task_id"],
            start_time=datetime.fromisoformat(row["start_time"]),
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            status=TaskStatus(row["status"]),
            output=row["output"],
            error=row["error"]
        )