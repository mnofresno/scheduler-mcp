import pytest
from mcp_scheduler.utils import parse_structured_schedule
from mcp_scheduler.config import Config
from mcp_scheduler.executor import Executor
from mcp_scheduler.persistence import Database
from mcp_scheduler.scheduler import Scheduler
from mcp_scheduler.task import Task, TaskType
import datetime

@pytest.mark.asyncio
async def test_structured_relative_schedule_seconds(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    executor = Executor(None, "gpt-3.5-turbo")
    scheduler = Scheduler(db, executor)
    await scheduler.start()
    schedule = {"schedule_type": "relative", "unit": "seconds", "amount": 12}
    task = Task(name="TestRelSec", schedule=schedule, type=TaskType.REMINDER, reminder_message="msg")
    t = await scheduler.add_task(task)
    # Check that the saved schedule is the structured dict
    assert t.schedule == schedule
    # Check that the parser returns the correct delay
    assert parse_structured_schedule(t.schedule) == "delay:12"
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = (t.next_run - now).total_seconds()
    assert 10 <= delta <= 14
    await scheduler.stop()

@pytest.mark.asyncio
async def test_structured_absolute_schedule(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    executor = Executor(None, "gpt-3.5-turbo")
    scheduler = Scheduler(db, executor)
    await scheduler.start()
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=20)).isoformat()
    schedule = {"schedule_type": "absolute", "datetime": future}
    task = Task(name="TestAbs", schedule=schedule, type=TaskType.REMINDER, reminder_message="msg")
    t = await scheduler.add_task(task)
    # Schedule should be the structured dict
    assert t.schedule == schedule
    # The parser should return delay:N
    parsed = parse_structured_schedule(t.schedule)
    assert parsed.startswith("delay:")
    delay = int(parsed.split(":")[1])
    assert 18 <= delay <= 22
    await scheduler.stop()

@pytest.mark.asyncio
async def test_structured_recurrent_schedule(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    executor = Executor(None, "gpt-3.5-turbo")
    scheduler = Scheduler(db, executor)
    await scheduler.start()
    cron = "0 9 * * 1"
    schedule = {"schedule_type": "recurrent", "cron": cron}
    task = Task(name="TestRec", schedule=schedule, type=TaskType.REMINDER, reminder_message="msg")
    t = await scheduler.add_task(task)
    assert t.schedule == schedule
    assert parse_structured_schedule(t.schedule) == cron
    await scheduler.stop()
