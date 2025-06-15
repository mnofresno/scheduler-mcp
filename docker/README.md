# MCP Scheduler Docker

## Build
```bash
docker build -t mcp-scheduler -f docker/Dockerfile .
```

## Run
```bash
# Create data directory for persistence
mkdir -p data

# Run with default configuration
docker run -d \
  --name mcp-scheduler \
  -p 8080:8080 -p 8081:8081 \
  -v $(pwd)/data:/data \
  mcp-scheduler

# Run with custom environment variables
docker run -d \
  --name mcp-scheduler \
  -p 8080:8080 -p 8081:8081 \
  -v $(pwd)/data:/data \
  -e MCP_SCHEDULER_PORT=8080 \
  -e MCP_WELL_KNOWN_PORT=8081 \
  -e MCP_SCHEDULER_ADDRESS=0.0.0.0 \
  -e MCP_SCHEDULER_TRANSPORT=sse \
  mcp-scheduler

# Run with custom config file
docker run -d \
  --name mcp-scheduler \
  -p 8080:8080 -p 8081:8081 \
  -v $(pwd)/data:/data \
  -v $(pwd)/config:/config \
  -e MCP_SCHEDULER_CONFIG_FILE=/config/config.json \
  mcp-scheduler
```

## Environment Variables

The following environment variables can be used to configure the server:

- `MCP_SCHEDULER_PORT`: Port for the MCP server (default: 8080)
- `MCP_WELL_KNOWN_PORT`: Port for the well-known endpoint (default: 8081)
- `MCP_SCHEDULER_ADDRESS`: Server address (default: 0.0.0.0)
- `MCP_SCHEDULER_TRANSPORT`: Transport mode (default: sse)
- `MCP_SCHEDULER_LOG_LEVEL`: Logging level (default: INFO)
- `MCP_SCHEDULER_LOG_FILE`: Log file path (default: /data/mcp_scheduler.log)
- `MCP_SCHEDULER_DB_PATH`: Database path (default: /data/scheduler.db)
- `MCP_SCHEDULER_CHECK_INTERVAL`: Task check interval in seconds (default: 5)
- `MCP_SCHEDULER_EXECUTION_TIMEOUT`: Task execution timeout in seconds (default: 300)
- `MCP_SCHEDULER_AI_MODEL`: AI model for AI tasks (default: gpt-4o)
- `OPENAI_API_KEY`: API key for OpenAI tasks (required for AI tasks)

## Stop
```bash
docker stop mcp-scheduler
```

## Remove
```bash
docker rm mcp-scheduler
``` 