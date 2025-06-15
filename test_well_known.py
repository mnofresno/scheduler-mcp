import pytest
from fastapi.testclient import TestClient
from mcp_scheduler.config import Config
from mcp_scheduler.executor import Executor
from mcp_scheduler.persistence import Database
from mcp_scheduler.scheduler import Scheduler
from mcp_scheduler.server import SchedulerServer


def test_well_known_schema(tmp_path):
    db_path = tmp_path / "db.sqlite"
    db = Database(str(db_path))
    config = Config()
    config.server_address = "127.0.0.1"
    config.server_port = 0
    config.transport = "sse"
    executor = Executor(None, config.ai_model)
    scheduler = Scheduler(db, executor)
    server = SchedulerServer(scheduler, config)
    client = TestClient(server.app)
    resp = client.get("/.well-known/mcp-schema.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    assert isinstance(data["tools"], list)
