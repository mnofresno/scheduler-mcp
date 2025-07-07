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
from mcp_scheduler.server import McpScheduler
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
    
    # Configure logging early
    config = Config() # Load config to get log level and file
    setup_logging(config.log_level, config.log_file)
    logger = logging.getLogger(__name__)
    logger.info(f"Using database path: {config.db_path}")

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
                    
        # Initialize components
        logger.info(f"Initializing Database with path: {config.db_path}")
        database = Database(config.db_path)
        logger.info("Database initialized successfully.")

<<<<<<< HEAD
        logger.info("Initializing Executor...")
        executor = Executor(config)
        logger.info("Executor initialized successfully.")
=======
        # If the transport is SSE, launch the well-known server in a separate thread
        if config.transport == "sse":
            log_to_stderr(f"Starting well-known server on port {config.server_port + 1}")
            threading.Thread(target=start_well_known_server, daemon=True).start()

        # Start the MCP server (this will block with stdio transport)
        log_to_stderr(f"Starting MCP server with {config.transport} transport")
        server.start()
>>>>>>> 25633b5 (fix(i18n): translate all comments to English for consistency)
        
        logger.info("Initializing McpScheduler...")
        server = McpScheduler(database, executor) # This will initialize Database and Scheduler
        logger.info("McpScheduler initialized successfully.")

        # Run the server
        logger.info(f"Starting server on {config.server_address}:{config.server_port}")
        server.run(host=config.server_address, port=config.server_port)
    except Exception as e:
        logger.critical(f"Fatal error during startup: {e}")
        if debug_mode:
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
