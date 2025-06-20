#!/bin/bash

docker build . -f docker/Dockerfile -t ghcr.io/mnofresno/scheduler-mcp:0.0.1 --load

docker push ghcr.io/mnofresno/scheduler-mcp:0.0.1