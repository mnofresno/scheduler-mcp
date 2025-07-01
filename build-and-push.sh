#!/bin/bash

docker build --platform linux/amd64 . -f docker/Dockerfile -t ghcr.io/mnofresno/scheduler-mcp:latest --load
docker build --platform linux/arm64 . -f docker/Dockerfile -t ghcr.io/mnofresno/scheduler-mcp:latest --load

docker push ghcr.io/mnofresno/scheduler-mcp:latest