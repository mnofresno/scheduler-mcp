# syntax=docker/dockerfile:1.4
FROM --platform=$BUILDPLATFORM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_SCHEDULER_NAME="mcp-scheduler" \
    MCP_SCHEDULER_VERSION="0.1.0" \
    MCP_SCHEDULER_ADDRESS="0.0.0.0" \
    MCP_SCHEDULER_TRANSPORT="sse" \
    MCP_SCHEDULER_LOG_LEVEL="INFO" \
    MCP_SCHEDULER_CHECK_INTERVAL="5" \
    MCP_SCHEDULER_EXECUTION_TIMEOUT="300"

# Install adduser for user creation (Debian/Ubuntu based)
RUN apt-get update && apt-get install -y --no-install-recommends adduser \
    && adduser --disabled-password --gecos "" --uid 1000 mcp \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only necessary files
COPY requirements.txt .
COPY main.py .
COPY mcp_scheduler/ ./mcp_scheduler/
# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    chown -R mcp:mcp /app

# Switch to non-root user
USER mcp

# Set entrypoint
ENTRYPOINT ["python", "main.py"] 