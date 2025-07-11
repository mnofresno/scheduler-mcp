"""
Entry point for MCP Scheduler.
"""
import asyncio
import argparse
import logging
import os
import signal
import sys
import traceback
import threading
import json
from concurrent.futures import ThreadPoolExecutor

from mcp_scheduler.config import Config
from mcp_scheduler.persistence import Database
from mcp_scheduler.executor import Executor
from mcp_scheduler.scheduler import Scheduler
from mcp_scheduler.server import SchedulerServer
from mcp_scheduler.utils import setup_logging

# Import our custom JSON parser utilities
try:
    from mcp_scheduler.json_parser import patch_fastmcp_parser, install_stdio_wrapper
except ImportError:
    # Define dummies if the module isn't available
    def patch_fastmcp_parser():
        return False
    def install_stdio_wrapper():
        return False

# Global variables for cleanup
scheduler = None
server = None
scheduler_thread = None
scheduler_loop = None
shutdown_event = threading.Event()

def log_to_stderr(message):
    """Log messages to stderr instead of stdout to avoid interfering with stdio transport."""
    print(message, file=sys.stderr, flush=True)

def handle_sigterm(signum, frame):
    """Handle SIGTERM signal."""
    log_to_stderr("Received SIGTERM, shutting down...")
    shutdown_event.set()
    if scheduler:
        scheduler.stop()
    if server:
        server.stop()
    if scheduler_thread and scheduler_thread.is_alive():
        scheduler_thread.join(timeout=5)
    if scheduler_loop and scheduler_loop.is_running():
        scheduler_loop.stop()
    sys.exit(0)

async def run_scheduler():
    """Run the scheduler in the background."""
    try:
        await scheduler.start()
        while not shutdown_event.is_set():
            await asyncio.sleep(1)
    except Exception as e:
        log_to_stderr(f"Error in scheduler: {str(e)}")
        if debug_mode:
            traceback.print_exc()
        raise
    finally:
        await scheduler.stop()

def run_loop():
    """Run the scheduler loop in a background thread."""
    global scheduler_loop
    try:
        scheduler_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(scheduler_loop)
        scheduler_loop.run_until_complete(run_scheduler())
    except Exception as e:
        log_to_stderr(f"Error in scheduler loop: {str(e)}")
        if debug_mode:
            traceback.print_exc()
    finally:
        if scheduler_loop and scheduler_loop.is_running():
            scheduler_loop.stop()
        if scheduler_loop and not scheduler_loop.is_closed():
            scheduler_loop.close()

def main():
    """Main entry point."""
    global scheduler, server, scheduler_thread, scheduler_loop
    
    parser = argparse.ArgumentParser(description="MCP Scheduler Server")
    parser.add_argument(
        "--address", 
        default=None,
        help="Server address (default: localhost or from config/env)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=None,
        help="Server port (default: 8080 or from config/env)"
    )
    parser.add_argument(
        "--transport", 
        choices=["sse", "stdio"], 
        default=None,
        help="Transport mode (sse or stdio) (default: sse or from config/env)"
    )
    parser.add_argument(
        "--log-level", 
        default=None,
        help="Logging level (default: INFO or from config/env)"
    )
    parser.add_argument(
        "--log-file", 
        default=None,
        help="Log file path (default: None or from config/env)"
    )
    parser.add_argument(
        "--db-path", 
        default=None,
        help="SQLite database path (default: scheduler.db or from config/env)"
    )
    parser.add_argument(
        "--config", 
        default=None,
        help="Path to JSON configuration file"
    )
    parser.add_argument(
        "--ai-model", 
        default=None,
        help="AI model to use for AI tasks (default: gpt-4o or from config/env)"
    )
    parser.add_argument(
        "--version", 
        action="store_true",
        help="Show version and exit"
    )
    parser.add_argument(
        "--debug", 
        action="store_true",
        help="Enable debug mode with full traceback"
    )
    parser.add_argument(
        "--fix-json", 
        action="store_true",
        help="Enable JSON fixing for malformed messages"
    )
    
    args = parser.parse_args()
    
    # Set environment variables for config
    if args.config:
        os.environ["MCP_SCHEDULER_CONFIG_FILE"] = args.config
    
    if args.address:
        os.environ["MCP_SCHEDULER_ADDRESS"] = args.address
    
    if args.port:
        os.environ["MCP_SCHEDULER_PORT"] = str(args.port)
    
    if args.transport:
        os.environ["MCP_SCHEDULER_TRANSPORT"] = args.transport
    
    if args.log_level:
        os.environ["MCP_SCHEDULER_LOG_LEVEL"] = args.log_level
    
    if args.log_file:
        os.environ["MCP_SCHEDULER_LOG_FILE"] = args.log_file
    
    if args.db_path:
        os.environ["MCP_SCHEDULER_DB_PATH"] = args.db_path
    
    if args.ai_model:
        os.environ["MCP_SCHEDULER_AI_MODEL"] = args.ai_model
    
    # Enable debug mode
    debug_mode = args.debug
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    try:
        # Install JSON fixing patches if requested or always in debug mode
        if args.fix_json or debug_mode:
            # Try to patch the FastMCP parser directly
            if not patch_fastmcp_parser():
                # If direct patching fails, use stdin wrapper as fallback
                if not install_stdio_wrapper():
                    # Last resort: replace stdin with our custom wrapper
                    log_to_stderr("Installing basic JSON fix wrapper")
                    sys.stdin = SafeJsonStdin(sys.stdin)
                    
        # Load configuration
        config = Config()
        
        # Show version and exit if requested
        if args.version:
            log_to_stderr(f"{config.server_name} version {config.server_version}")
            sys.exit(0)
        
        # Configure logging - ensure it goes to a file or stderr, not stdout
        if not config.log_file and config.transport == "stdio":
            # Force a log file when using stdio transport if none was specified
            config.log_file = "mcp_scheduler.log"
            
        setup_logging(config.log_level, config.log_file)
        
        # Initialize components
        database = Database(config.db_path)
        executor = Executor(None, config.ai_model)
        scheduler = Scheduler(database, executor)
        server = SchedulerServer(scheduler, config)
        
        # Start scheduler in background thread
        scheduler_thread = threading.Thread(target=run_loop, daemon=True)
        scheduler_thread.start()
        log_to_stderr("Scheduler started in background thread")
        
        # Start server
        log_to_stderr(f"Starting server on {config.server_address}:{config.server_port} using {config.transport} transport")
        server.start()

    except KeyboardInterrupt:
        log_to_stderr("Interrupted by user")
        shutdown_event.set()
        if scheduler_thread and scheduler_thread.is_alive():
            scheduler_thread.join(timeout=5)
        sys.exit(0)
    except Exception as e:
        log_to_stderr(f"Error during initialization: {e}")
        if debug_mode:
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
