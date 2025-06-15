# MCP Scheduler

A robust task scheduler server built with Model Context Protocol (MCP) for scheduling and managing various types of automated tasks.

![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Overview

MCP Scheduler is a versatile task automation system that allows you to schedule and run different types of tasks:

- **Shell Commands**: Execute system commands on a schedule
- **API Calls**: Make HTTP requests to external services
- **AI Tasks**: Generate content through OpenAI models
- **Reminders**: Display desktop notifications with sound

The scheduler uses cron expressions for flexible timing and provides a complete history of task executions. It's built on the Model Context Protocol (MCP), making it easy to integrate with AI assistants and other MCP-compatible clients.

## Features

- **Multiple Task Types**: Support for shell commands, API calls, AI content generation, and desktop notifications
- **Cron Scheduling**: Familiar cron syntax for precise scheduling control
- **Run Once or Recurring**: Option to run tasks just once or repeatedly on schedule
- **Execution History**: Track successful and failed task executions
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Interactive Notifications**: Desktop alerts with sound for reminder tasks
- **MCP Integration**: Seamless connection with AI assistants and tools
- **Robust Error Handling**: Comprehensive logging and error recovery

## Installation

### Prerequisites

- Python 3.10 or higher
- [uv](https://astral.sh/uv) (recommended package manager)

### Installing uv (recommended)

```bash
# For Mac/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# For Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After installing uv, restart your terminal to ensure the command is available.

### Project Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/mcp-scheduler.git
cd mcp-scheduler

# Create and activate a virtual environment with uv
uv venv
source .venv/bin/activate  # On Unix/MacOS
# or
.venv\Scripts\activate     # On Windows

# Install dependencies with uv
uv pip install -r requirements.txt
```

### Standard pip installation (alternative)

If you prefer using standard pip:

```bash
# Clone the repository
git clone https://github.com/yourusername/mcp-scheduler.git
cd mcp-scheduler

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Unix/MacOS
# or
.venv\Scripts\activate     # On Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Running the Server

```bash
# Run with default settings (stdio transport)
python main.py

# Run with server transport on specific port
python main.py --transport sse --port 8080

# Run with debug mode for detailed logging
python main.py --debug
```

### What is SSE Transport?

SSE (Server-Sent Events) is an HTTP-based protocol that allows the server to push
events to the client over a single long-lived connection. When running the
scheduler with `--transport sse`, FastMCP exposes an HTTP endpoint that streams
JSON-RPC responses using SSE. This mode is suitable when integrating with tools
that expect an HTTP interface rather than standard input/output.

### Integrating with Claude Desktop or other MCP Clients

To use your MCP Scheduler with Claude Desktop:

1. Make sure you have Claude Desktop installed
2. Open your Claude Desktop App configuration at:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
3. Create the file if it doesn't exist, and add your server:

```json
{
  "mcpServers": [
    {
      "type": "stdio",
      "name": "MCP Scheduler",
      "command": "python",
      "args": ["/path/to/your/mcp-scheduler/main.py"]
    }
  ]
}
```

Alternatively, use the `fastmcp` utility if you're using the FastMCP library:

```bash
# Install your server in Claude Desktop
fastmcp install main.py --name "Task Scheduler"
```

### Command Line Options

```
--address        Server address (default: localhost)
--port           Server port (default: 8080)
--transport      Transport mode (sse or stdio) (default: stdio)
--log-level      Logging level (default: INFO)
--log-file       Log file path (default: mcp_scheduler.log)
--db-path        SQLite database path (default: scheduler.db)
--config         Path to JSON configuration file
--ai-model       AI model to use for AI tasks (default: gpt-4o)
--version        Show version and exit
--debug          Enable debug mode with full traceback
--fix-json       Enable JSON fixing for malformed messages
```

### Configuration File

You can use a JSON configuration file instead of command-line arguments:

```json
{
  "server": {
    "name": "mcp-scheduler",
    "version": "0.1.0",
    "address": "localhost",
    "port": 8080,
    "transport": "sse"
  },
  "database": {
    "path": "scheduler.db"
  },
  "logging": {
    "level": "INFO",
    "file": "mcp_scheduler.log"
  },
  "scheduler": {
    "check_interval": 5,
    "execution_timeout": 300
  },
  "ai": {
    "model": "gpt-4o",
    "openai_api_key": "your-api-key"
  }
}
```

## MCP Tool Functions

The MCP Scheduler provides the following tools:

### Task Management

- `list_tasks`: Get all scheduled tasks
- `get_task`: Get details of a specific task
- `add_command_task`: Add a new shell command task
- `add_api_task`: Add a new API call task
- `add_ai_task`: Add a new AI task
- `add_reminder_task`: Add a new reminder task with desktop notification
- `update_task`: Update an existing task
- `remove_task`: Delete a task
- `enable_task`: Enable a disabled task
- `disable_task`: Disable an active task
- `run_task_now`: Run a task immediately

### Execution and Monitoring

- `get_task_executions`: Get execution history for a task
- `get_server_info`: Get server information

## Cron Expression Guide

MCP Scheduler uses standard cron expressions for scheduling. Here are some examples:

- `0 0 * * *` - Daily at midnight
- `0 */2 * * *` - Every 2 hours
- `0 9-17 * * 1-5` - Every hour from 9 AM to 5 PM, Monday to Friday
- `0 0 1 * *` - At midnight on the first day of each month
- `0 0 * * 0` - At midnight every Sunday

## Environment Variables

The scheduler can be configured using environment variables:

- `MCP_SCHEDULER_NAME`: Server name (default: mcp-scheduler)
- `MCP_SCHEDULER_VERSION`: Server version (default: 0.1.0)
- `MCP_SCHEDULER_ADDRESS`: Server address (default: localhost)
- `MCP_SCHEDULER_PORT`: Server port (default: 8080)
- `MCP_SCHEDULER_TRANSPORT`: Transport mode (default: stdio)
- `MCP_SCHEDULER_LOG_LEVEL`: Logging level (default: INFO)
- `MCP_SCHEDULER_LOG_FILE`: Log file path
- `MCP_SCHEDULER_DB_PATH`: Database path (default: scheduler.db)
- `MCP_SCHEDULER_CHECK_INTERVAL`: How often to check for tasks (default: 5 seconds)
- `MCP_SCHEDULER_EXECUTION_TIMEOUT`: Task execution timeout (default: 300 seconds)
- `MCP_SCHEDULER_AI_MODEL`: OpenAI model for AI tasks (default: gpt-4o)
- `OPENAI_API_KEY`: API key for OpenAI tasks

## Server Port

The MCP Scheduler exposes its API and the auto-discovery endpoint on a single port.

* **MCP Server Port:**
  The server listens on the port defined by the environment variable `MCP_SCHEDULER_PORT` (default: `8080`).
  The well-known schema is available at `http://<address>:<MCP_SCHEDULER_PORT>/.well-known/mcp-schema.json`.

## Examples

### Adding a Shell Command Task

```python
await scheduler.add_command_task(
    name="Backup Database",
    schedule="0 0 * * *",  # Midnight every day
    command="pg_dump -U postgres mydb > /backups/mydb_$(date +%Y%m%d).sql",
    description="Daily database backup",
    do_only_once=False  # Recurring task
)
```

### Adding an API Task

```python
await scheduler.add_api_task(
    name="Fetch Weather Data",
    schedule="0 */6 * * *",  # Every 6 hours
    api_url="https://api.weather.gov/stations/KJFK/observations/latest",
    api_method="GET",
    description="Get latest weather observations",
    do_only_once=False
)
```

### Adding an AI Task

```python
await scheduler.add_ai_task(
    name="Generate Weekly Report",
    schedule="0 9 * * 1",  # 9 AM every Monday
    prompt="Generate a summary of the previous week's sales data.",
    description="Weekly sales report generation",
    do_only_once=False
)
```

### Adding a Reminder Task

```python
await scheduler.add_reminder_task(
    name="Team Meeting",
    schedule="30 9 * * 2,4",  # 9:30 AM every Tuesday and Thursday
    message="Don't forget the team standup meeting!",
    title="Meeting Reminder",
    do_only_once=False
)
```

## MCP Auto-discovery Endpoint

When running in SSE (HTTP) mode, MCP Scheduler exposes a well-known endpoint for tool/schema auto-discovery:

- **Endpoint:** `/.well-known/mcp-schema.json` on the same port as the MCP API.
- **Purpose:** Allows clients and AI assistants to discover all available MCP tools and their parameters automatically.

### Example

If you run:

```bash
python main.py --transport sse --port 8080
```

You can access the schema at:

```
http://localhost:8080/.well-known/mcp-schema.json
```

### Example Response

```json
{
  "tools": [
    {
      "name": "list_tasks",
      "description": "List all scheduled tasks.",
      "endpoint": "list_tasks",
      "method": "POST",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "add_command_task",
      "description": "Add a new shell command task.",
      "endpoint": "add_command_task",
      "method": "POST",
      "parameters": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "schedule": {"type": "string"},
          "command": {"type": "string"},
          "description": {"type": "string"},
          "enabled": {"type": "boolean"},
          "do_only_once": {"type": "boolean"}
        },
        "required": ["name", "schedule", "command"],
        "additionalProperties": false
      }
    }
    // ... more tools ...
  ]
}
```

This schema is generated automatically from the registered MCP tools and always reflects the current server capabilities.

## Using the SSE API (Server-Sent Events)

### Client Configuration

To use the scheduler through SSE, you need to ensure that:

1. The server is running in SSE mode:
```bash
python main.py --transport sse --port 8080
```

2. The client has access to the following endpoints:
   - `http://<host>:<port>/.well-known/mcp-schema.json` - To discover available tools
   - `http://<host>:<port>/mcp/sse` - For SSE connection
   - `http://<host>:<port>/mcp/messages` - To send messages to the server

### Example Usage with curl

```bash
# 1. First, get the schema
curl http://localhost:8080/.well-known/mcp-schema.json

# 2. Create a reminder task using the messages endpoint
curl -X POST http://localhost:8080/mcp/messages \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "add_reminder_task",
    "params": {
      "name": "Important Reminder",
      "schedule": "*/1 * * * *",
      "message": "Time for your reminder!",
      "title": "Reminder",
      "do_only_once": true
    }
  }'
```

### Example Usage with Python

```python
import asyncio
import aiohttp
import json

async def schedule_reminder():
    # Server base URL
    base_url = "http://localhost:8080"
    
    # 1. Create the task using the messages endpoint
    async with aiohttp.ClientSession() as session:
        # Prepare JSON-RPC message
        message = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "add_reminder_task",
            "params": {
                "name": "Reminder in 1 minute",
                "schedule": "*/1 * * * *",  # Every minute
                "message": "Time for your reminder!",
                "title": "Important Reminder",
                "do_only_once": true
            }
        }
        
        # Send the request
        async with session.post(
            f"{base_url}/mcp/messages",
            json=message,
            headers={"Content-Type": "application/json"}
        ) as response:
            result = await response.json()
            print(f"Server response: {result}")

# Run the example
asyncio.run(schedule_reminder())
```

### Common Issues and Solutions

1. **SSE Connection Error**
   - Ensure the server is running and accessible
   - Verify the port is open and not blocked by a firewall
   - Check that the server URL is correct
   - If using Docker, ensure containers are on the same network and ports are properly mapped

2. **Schedule Format**
   - Use valid cron expressions (e.g., `*/1 * * * *` for every minute)
   - For one-time tasks, use `do_only_once: true`
   - Common schedule examples:
     - `*/1 * * * *` - Every minute
     - `0 */1 * * *` - Every hour
     - `0 0 * * *` - Once a day at midnight

3. **Docker Configuration**
   If using Docker, ensure your `docker-compose.yml` includes:

```yaml
services:
  scheduler:
    image: mcp-scheduler
    ports:
      - "8080:8080"
    environment:
      - MCP_SCHEDULER_TRANSPORT=sse
      - MCP_SCHEDULER_PORT=8080
      - MCP_SCHEDULER_ADDRESS=0.0.0.0
    networks:
      - mcp_network

networks:
  mcp_network:
    driver: bridge
```

4. **Status Verification**
   To verify the server is working correctly:

```bash
# Verify server response
curl http://localhost:8080/.well-known/mcp-schema.json

# Verify existing tasks
curl -X POST http://localhost:8080/mcp/messages \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "list_tasks",
    "params": {}
  }'
```

### Important Notes

1. **Security**: 
   - By default, the server listens on `0.0.0.0` when running in Docker
   - In production, consider using HTTPS and authentication
   - Limit access to necessary ports

2. **Performance**:
   - The SSE server maintains an open connection
   - Consider the maximum number of simultaneous connections
   - Monitor resource usage

3. **Error Handling**:
   - Implement automatic reconnection in the client
   - Handle timeouts appropriately
   - Verify server responses

4. **Debugging**:
   - Use `--debug` when starting the server for detailed logs
   - Check server logs for specific errors
   - Verify network connectivity between client and server

## Development

If you want to contribute or develop the MCP Scheduler further, here are some additional commands:

```bash
# Install the MCP SDK for development
uv pip install "mcp[cli]>=1.4.0"

# Or for FastMCP (alternative implementation)
uv pip install fastmcp

# Testing your MCP server
# With the MCP Inspector tool
mcp inspect --stdio -- python main.py

# Or with a simple MCP client
python -m mcp.client.stdio python main.py
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built on the [Model Context Protocol](https://modelcontextprotocol.io/)
- Uses [croniter](https://github.com/kiorky/croniter) for cron parsing
- Uses [OpenAI API](https://openai.com/blog/openai-api) for AI tasks
- Uses [FastMCP](https://github.com/jlowin/fastmcp) for enhanced MCP functionality

### MCP Client Configuration in Docker

When using the scheduler in a Docker environment, special attention must be paid to the client configuration. Based on the server implementation and test cases, here's the correct setup:

1. **Server Configuration (docker-compose.yml)**
```yaml
services:
  scheduler_mcp:
    image: ghcr.io/mnofresno/scheduler-mcp:0.0.1
    restart: unless-stopped
    environment:
      - MCP_SCHEDULER_PORT=8085
      - MCP_SCHEDULER_ADDRESS=0.0.0.0
      - MCP_SCHEDULER_TRANSPORT=sse
    networks:
      - mcp_network

networks:
  mcp_network:
    driver: bridge
```

2. **MCP Client Configuration**
```json
{
  "id": "scheduler",
  "server_url": "http://scheduler_mcp:8085",
  "transport": "sse"
}
```

3. **Available Endpoints**
Based on the server implementation (`server.py`) and test cases (`test_well_known.py`), these are the ONLY valid endpoints:

- Schema Discovery:
  ```
  http://scheduler_mcp:8085/.well-known/mcp-schema.json
  ```
- SSE Connection:
  ```
  http://scheduler_mcp:8085/mcp/sse
  ```
- Message Endpoint:
  ```
  http://scheduler_mcp:8085/mcp/messages
  ```

4. **Important Notes for Docker Setup**

- **Network Configuration**:
  - Both client and server containers MUST be on the same Docker network
  - Use the container name (`scheduler_mcp`) as the hostname in URLs
  - The port (8085) must match the `MCP_SCHEDULER_PORT` environment variable

- **Schema Validation**:
  - The server implements schema validation through `test_well_known.py`
  - Only tools registered in `server.py` are available
  - The schema endpoint (`/.well-known/mcp-schema.json`) is the source of truth for available tools

- **Common Mistakes to Avoid**:
  - Don't use `localhost` in Docker - use the container name
  - Don't assume additional endpoints - only use the documented ones
  - Don't modify the base paths (`/mcp/` and `/.well-known/`) - they are hardcoded in the server
  - Don't use different ports than configured in the environment variables

5. **Verification Steps**

```bash
# 1. Verify the schema endpoint is accessible
curl http://scheduler_mcp:8085/.well-known/mcp-schema.json

# 2. Verify the server is running and accessible
curl -X POST http://scheduler_mcp:8085/mcp/messages \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "get_server_info",
    "params": {}
  }'

# 3. Check network connectivity
docker exec your_client_container ping scheduler_mcp
```

6. **Troubleshooting Docker Issues**

If you encounter connection issues:

1. **Verify Network**:
```bash
# Check if containers are on the same network
docker network inspect mcp_network

# Check container logs
docker logs scheduler_mcp
```

2. **Verify Port Mapping**:
```bash
# Check if the port is actually listening
docker exec scheduler_mcp netstat -tulpn | grep 8085
```

3. **Check Environment Variables**:
```bash
# Verify environment variables in the container
docker exec scheduler_mcp env | grep MCP_SCHEDULER
```

4. **Common Error Messages and Solutions**:

```
Error: "Connection refused"
Solution: Verify container name and port in server_url

Error: "SSE connection error"
Solution: Check if MCP_SCHEDULER_TRANSPORT=sse is set

Error: "Schema not found"
Solution: Verify the /.well-known/mcp-schema.json endpoint is accessible
```

7. **Security Considerations**

- The server listens on `0.0.0.0` by default in Docker
- Use Docker networks to isolate the communication
- Consider using Docker secrets for sensitive configuration
- In production, consider adding authentication to the MCP endpoints
