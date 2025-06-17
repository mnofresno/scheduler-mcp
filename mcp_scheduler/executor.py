"""
Task executor for MCP Scheduler.
"""
import asyncio
import logging
import shlex
import subprocess
import platform
import os
from datetime import datetime
import aiohttp
from typing import Optional, Tuple

import openai

from .task import Task, TaskExecution, TaskStatus, TaskType

logger = logging.getLogger(__name__)


class Executor:
    """Task executor for running scheduled tasks."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        """Initialize the task executor."""
        self.api_key = api_key
        self.ai_model = model
        self.execution_timeout = 300  # 5 minutes default timeout
        self.is_windows = platform.system() == "Windows"
        
        if api_key:
            openai.api_key = api_key
    
    async def execute_task(self, task: Task) -> TaskExecution:
        """Execute a task based on its type."""
        logger.info(f"Executing task: {task.id} ({task.name})")
        
        execution = TaskExecution(task_id=task.id)
        
        try:
            if task.type.value == "shell_command":
                output, error = await self._execute_shell_command(task.command)
                if error:
                    execution.status = TaskStatus.FAILED
                    execution.error = error
                else:
                    execution.status = TaskStatus.COMPLETED
                    execution.output = output
                    
            elif task.type.value == "api_call":
                output, error = await self._execute_api_call(
                    task.api_url, 
                    task.api_method, 
                    task.api_headers, 
                    task.api_body
                )
                if error:
                    execution.status = TaskStatus.FAILED
                    execution.error = error
                else:
                    execution.status = TaskStatus.COMPLETED
                    execution.output = output
                    
            elif task.type.value == "ai":
                output, error = await self._execute_ai_task(task.prompt)
                if error:
                    execution.status = TaskStatus.FAILED
                    execution.error = error
                else:
                    execution.status = TaskStatus.COMPLETED
                    execution.output = output
                    
            elif task.type.value == "reminder":
                output, error = await self._execute_reminder_task(
                    task.reminder_title or task.name,
                    task.reminder_message
                )
                if error:
                    execution.status = TaskStatus.FAILED
                    execution.error = error
                else:
                    execution.status = TaskStatus.COMPLETED
                    execution.output = output
            
            else:
                execution.status = TaskStatus.FAILED
                execution.error = f"Unsupported task type: {task.type.value}"
                
        except Exception as e:
            logger.exception(f"Error executing task {task.id}")
            execution.status = TaskStatus.FAILED
            execution.error = str(e)
        
        execution.end_time = datetime.utcnow()
        return execution
    
    async def _execute_shell_command(self, command: str) -> Tuple[Optional[str], Optional[str]]:
        """Execute a shell command with timeout."""
        if not command:
            return None, "No command specified"
        
        # Determine if we need to use shell mode
        use_shell = self.is_windows
        
        # These commands are shell builtins and need shell=True
        shell_commands = ['start', 'cd', 'dir', 'echo', 'set', 'type', 'copy', 'del', 'md', 'rd', 'ren', 'cls']
        
        # If command starts with any of these, use shell mode
        if any(command.strip().lower().startswith(cmd) for cmd in shell_commands):
            use_shell = True
        
        # If pipe or redirect is in command, use shell mode
        if '|' in command or '>' in command or '<' in command:
            use_shell = True
            
        logger.info(f"Executing command: {command} (shell mode: {use_shell})")
        
        try:
            if use_shell:
                # Use shell mode for Windows or shell-specific commands
                if self.is_windows:
                    # Force cmd.exe on Windows
                    full_command = f"cmd.exe /c {command}"
                else:
                    full_command = command
                
                process = await asyncio.create_subprocess_shell(
                    full_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=True
                )
            else:
                # Use direct execution for standard commands
                try:
                    args = shlex.split(command)
                except ValueError as e:
                    return None, f"Invalid command syntax: {str(e)}"
                
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=self.execution_timeout
                )
                
                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    return None, f"Command failed with exit code {process.returncode}: {error_msg}"
                
                return stdout.decode().strip(), None
                
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except Exception:
                    pass
                return None, f"Command timed out after {self.execution_timeout} seconds"
                
        except Exception as e:
            return None, f"Failed to execute command: {str(e)}"
    
    async def _execute_api_call(self, url: str, method: str, headers: dict, body: dict) -> Tuple[Optional[str], Optional[str]]:
        """Execute an API call."""
        if not url:
            return None, "No URL specified"
        
        if not method:
            method = "GET"
            
        method = method.upper()
        
        try:
            async with aiohttp.ClientSession() as session:
                request_kwargs = {
                    "headers": headers or {},
                }
                
                if method in ["POST", "PUT", "PATCH"] and body:
                    request_kwargs["json"] = body
                
                async with session.request(
                    method, 
                    url, 
                    **request_kwargs,
                    timeout=aiohttp.ClientTimeout(total=self.execution_timeout)
                ) as response:
                    response_text = await response.text()
                    
                    if response.status >= 400:
                        return None, f"API call failed with status {response.status}: {response_text}"
                    
                    return response_text, None
                    
        except aiohttp.ClientError as e:
            return None, f"API call failed: {str(e)}"
        except asyncio.TimeoutError:
            return None, f"API call timed out after {self.execution_timeout} seconds"
    
    async def _execute_ai_task(self, prompt: str) -> Tuple[Optional[str], Optional[str]]:
        """Execute an AI task using OpenAI."""
        if not prompt:
            return None, "No prompt specified"
        
        if not self.api_key:
            return None, "No API key configured for AI tasks"
        
        try:
            completion = await asyncio.to_thread(
                openai.chat.completions.create,
                model=self.ai_model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant executing scheduled tasks."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000
            )
            
            return completion.choices[0].message.content, None
            
        except Exception as e:
            return None, f"AI task failed: {str(e)}"
    
    async def _execute_reminder_task(self, title: str, message: str) -> Tuple[Optional[str], Optional[str]]:
        """Execute a reminder task that displays a desktop notification with sound."""
        if not message:
            return None, "No message specified for reminder"
        
        # Always log reminders since we're running in a server environment
        logger.info(f"REMINDER: {title} - {message}")
        return f"Reminder logged: {title} - {message}", None

    def run_shell(self, command: str):
        """Public wrapper for _execute_shell_command for testing purposes."""
        return self._execute_shell_command(command)