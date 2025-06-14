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
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  mcp-scheduler

# Run with custom environment variables
docker run -d \
  --name mcp-scheduler \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  --env-file docker/env.example \
  mcp-scheduler

# Run with custom config file
docker run -d \
  --name mcp-scheduler \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -v $(pwd)/config:/config \
  -e MCP_SCHEDULER_CONFIG_FILE=/config/config.json \
  mcp-scheduler
```

## Stop
```bash
docker stop mcp-scheduler
```

## Remove
```bash
docker rm mcp-scheduler
``` 