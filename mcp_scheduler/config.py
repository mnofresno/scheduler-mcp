"""
Configuration handling for MCP Scheduler.
"""
import os
import json
from typing import Optional, Dict, Any
from pathlib import Path


class Config:
    """Configuration handler for MCP Scheduler."""
    
    def __init__(self):
        """Initialize configuration with default values."""
        # Server configuration
        self.server_name = os.environ.get("MCP_SCHEDULER_NAME", "mcp-scheduler")
        self.server_version = os.environ.get("MCP_SCHEDULER_VERSION", "0.1.0")
        self.server_address = os.environ.get("MCP_SCHEDULER_ADDRESS", "0.0.0.0")  # Changed to 0.0.0.0 to allow external connections
        self.server_port = int(os.environ.get("MCP_SCHEDULER_PORT", "8080"))
        self.transport = os.environ.get("MCP_SCHEDULER_TRANSPORT", "sse")  # Changed default to sse
        self.strict_json = os.environ.get("MCP_SCHEDULER_STRICT_JSON", "true").lower() == "true"  # Changed default to true
        
        # Database configuration
        self.db_path = os.environ.get("MCP_SCHEDULER_DB_PATH", "scheduler.db")
        
        # Logging configuration
        self.log_level = os.environ.get("MCP_SCHEDULER_LOG_LEVEL", "INFO")
        self.log_file = os.environ.get("MCP_SCHEDULER_LOG_FILE", None)  # Changed to None to log to stdout by default
        
        # Scheduler configuration
        self.check_interval = int(os.environ.get("MCP_SCHEDULER_CHECK_INTERVAL", "5"))
        self.execution_timeout = int(os.environ.get("MCP_SCHEDULER_EXECUTION_TIMEOUT", "300"))
        
        # Base path for endpoints
        self.base_path = os.environ.get("MCP_SCHEDULER_BASE_PATH", "/mcp")
        
        # Heartbeat configuration
        self.heartbeat_interval = int(os.environ.get("MCP_SCHEDULER_HEARTBEAT_INTERVAL", "5"))
        self.session_timeout = int(os.environ.get("MCP_SCHEDULER_SESSION_TIMEOUT", "300"))
        
        # AI configuration
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", None)
        self.ai_model = os.environ.get("MCP_SCHEDULER_AI_MODEL", "gpt-4")  # Fixed model name
        
        # Reminder configuration
        self.reminder_delay_seconds = int(os.environ.get("MCP_SCHEDULER_REMINDER_DELAY_SECONDS", "10"))
        
        # Load config from file if provided
        config_file = os.environ.get("MCP_SCHEDULER_CONFIG_FILE", None)
        if config_file:
            self.load_config_file(config_file)
    
    def load_config_file(self, config_path: str) -> None:
        """Load configuration from a JSON file."""
        path = Path(config_path)
        if not path.exists():
            return
        
        try:
            with open(path, "r") as f:
                config = json.load(f)
                
            # Server configuration
            self.server_name = config.get("server", {}).get("name", self.server_name)
            self.server_version = config.get("server", {}).get("version", self.server_version)
            self.server_address = config.get("server", {}).get("address", self.server_address)
            self.server_port = config.get("server", {}).get("port", self.server_port)
            self.transport = config.get("server", {}).get("transport", self.transport)
            self.strict_json = config.get("server", {}).get("strict_json", self.strict_json)
            
            # Database configuration
            self.db_path = config.get("database", {}).get("path", self.db_path)
            
            # Logging configuration
            self.log_level = config.get("logging", {}).get("level", self.log_level)
            self.log_file = config.get("logging", {}).get("file", self.log_file)
            
            # Scheduler configuration
            self.check_interval = config.get("scheduler", {}).get("check_interval", self.check_interval)
            self.execution_timeout = config.get("scheduler", {}).get("execution_timeout", self.execution_timeout)
            
            # Base path for endpoints
            self.base_path = config.get("scheduler", {}).get("base_path", self.base_path)
            
            # Heartbeat configuration
            self.heartbeat_interval = config.get("scheduler", {}).get("heartbeat_interval", self.heartbeat_interval)
            self.session_timeout = config.get("scheduler", {}).get("session_timeout", self.session_timeout)
            
            # AI configuration
            self.openai_api_key = config.get("ai", {}).get("openai_api_key", self.openai_api_key)
            self.ai_model = config.get("ai", {}).get("model", self.ai_model)
            
            # Reminder configuration
            self.reminder_delay_seconds = config.get("scheduler", {}).get("reminder_delay_seconds", self.reminder_delay_seconds)
            
        except Exception as e:
            print(f"Error loading config file: {e}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the configuration to a dictionary."""
        return {
            "server": {
                "name": self.server_name,
                "version": self.server_version,
                "address": self.server_address,
                "port": self.server_port,
                "transport": self.transport,
                "strict_json": self.strict_json
            },
            "database": {
                "path": self.db_path
            },
            "logging": {
                "level": self.log_level,
                "file": self.log_file
            },
            "scheduler": {
                "check_interval": self.check_interval,
                "execution_timeout": self.execution_timeout,
                "base_path": self.base_path,
                "heartbeat_interval": self.heartbeat_interval,
                "session_timeout": self.session_timeout,
                "reminder_delay_seconds": self.reminder_delay_seconds
            },
            "ai": {
                "model": self.ai_model,
                # Don't include API key in output
            }
        }