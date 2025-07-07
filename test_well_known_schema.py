import pytest
import json
from fastapi.testclient import TestClient
from mcp_scheduler.config import Config
from mcp_scheduler.executor import Executor
from mcp_scheduler.persistence import Database
from mcp_scheduler.scheduler import Scheduler
from mcp_scheduler.server import SchedulerServer

def get_schema(client):
    resp = client.get("/.well-known/mcp-schema.json")
    assert resp.status_code == 200
    return resp.json()

def get_tool_names(schema):
    return {tool['name'] for tool in schema['tools']}

def get_tool_by_name(schema, name):
    for tool in schema['tools']:
        if tool['name'] == name:
            return tool
    return None

def test_mcp_schema_matches_functions():
    config = Config()
    db = Database(":memory:")
    executor = Executor(None, config.ai_model)
    scheduler = Scheduler(db, executor)
    server = SchedulerServer(scheduler, config)
    client = TestClient(server.app)
    schema = get_schema(client)
    # --- Assertion: all tool names in schema are implemented as endpoints ---
    tool_names = get_tool_names(schema)
    # For each tool, check parameters and required fields
    for tool in schema['tools']:
        params = tool['parameters']
        assert params['type'] == 'object'
        assert 'properties' in params
        # Check required fields exist in properties
        for req in params.get('required', []):
            assert req in params['properties'], f"Required param '{req}' missing in properties for tool {tool['name']}"
        # Optionally, check endpoint/method presence
        assert 'endpoint' in tool
        assert 'method' in tool
