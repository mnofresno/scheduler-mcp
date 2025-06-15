"""
Task model implementation for MCP Scheduler.
"""
from __future__ import annotations

import uuid
import re
from datetime import datetime, UTC
from enum import Enum
from typing import Literal, Optional, List, Dict, Any

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    """Status of a scheduled task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DISABLED = "disabled"


class TaskType(str, Enum):
    """Type of a scheduled task."""
    SHELL_COMMAND = "shell_command"
    API_CALL = "api_call"
    AI = "ai"
    REMINDER = "reminder"  # New task type for reminders


def sanitize_ascii(text: str) -> str:
    """Strips non-ASCII characters from a string."""
    if not text:
        return text
    return re.sub(r'[^\x00-\x7F]+', '', text)


class Task(BaseModel):
    """Model representing a scheduled task."""
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    name: str
    schedule: str
    type: TaskType = TaskType.SHELL_COMMAND
    command: Optional[str] = None
    api_url: Optional[str] = None
    api_method: Optional[str] = None
    api_headers: Optional[Dict[str, str]] = None
    api_body: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None
    description: Optional[str] = None
    enabled: bool = True
    do_only_once: bool = True  # New field: Default to run only once
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Reminder-specific fields
    reminder_title: Optional[str] = None
    reminder_message: Optional[str] = None

    @field_validator("name", "command", "prompt", "description", "reminder_title", "reminder_message", mode="before")
    def validate_ascii_fields(cls, v):
        """Ensure all user-visible text fields contain only ASCII characters."""
        if isinstance(v, str):
            return sanitize_ascii(v)
        return v

    @field_validator("command")
    def validate_command(cls, v, info):
        """Validate that a command is provided for shell_command tasks."""
        if info.data.get("type") == TaskType.SHELL_COMMAND and not v:
            raise ValueError("A command must be provided for shell_command tasks.")
        return v
    
    @field_validator("api_url")
    def validate_api_url(cls, v, info):
        """Validate that API URL is provided for api_call tasks."""
        if info.data.get("type") == TaskType.API_CALL and not v:
            raise ValueError("A API URL must be provided for api_call tasks.")
        return v

    @field_validator("prompt")
    def validate_prompt(cls, v, info):
        """Validate that a prompt is provided for AI tasks."""
        if info.data.get("type") == TaskType.AI and not v:
            raise ValueError("Prompt is required for AI tasks")
        return v
    
    @field_validator("reminder_message")
    def validate_reminder_message(cls, v, info):
        """Validate that a message is provided for reminder tasks."""
        if info.data.get("type") == TaskType.REMINDER and not v:
            raise ValueError("Message is required for reminder tasks")
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the task to a dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "schedule": self.schedule,
            "type": self.type.value,
            "command": self.command,
            "api_url": self.api_url,
            "api_method": self.api_method,
            "api_headers": self.api_headers,
            "api_body": self.api_body,
            "prompt": self.prompt,
            "description": self.description,
            "enabled": self.enabled,
            "do_only_once": self.do_only_once,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "reminder_title": self.reminder_title,
            "reminder_message": self.reminder_message
        }


class TaskExecution(BaseModel):
    """Model representing a task execution."""
    id: str = Field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:12]}")
    task_id: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: Optional[datetime] = None
    status: TaskStatus = TaskStatus.RUNNING
    output: Optional[str] = None
    error: Optional[str] = None
    
    @field_validator("output", "error", mode="before")
    def validate_ascii_output(cls, v):
        """Ensure output and error fields contain only ASCII characters."""
        if isinstance(v, str):
            return sanitize_ascii(v)
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the execution to a dictionary for serialization."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "output": self.output,
            "error": self.error
        }