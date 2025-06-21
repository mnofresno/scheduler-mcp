#!/bin/bash

docker build . -f docker/Dockerfile -t ghcr.io/mnofresno/scheduler-mcp:latest --load

docker push ghcr.io/mnofresno/scheduler-mcp:latest