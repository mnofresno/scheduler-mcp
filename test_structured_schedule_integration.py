import pytest
from mcp_scheduler.utils import parse_relative_time_to_cron
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
    schedule_str = parse_relative_time_to_cron(f"in {schedule['amount']} {schedule['unit']}")
    task = Task(name="TestRelSec", schedule=schedule_str, type=TaskType.REMINDER, reminder_message="msg")
    t = await scheduler.add_task(task)
    # The schedule field should be the cron string
    assert t.schedule == schedule_str
    # The parser should return a valid cron string
    assert isinstance(parse_relative_time_to_cron(t.schedule), str)
    # Optionally, check that next_run is a datetime in the future
    now = datetime.datetime.now(datetime.timezone.utc)
    assert t.next_run > now
    await scheduler.stop()

@pytest.mark.asyncio
async def test_structured_absolute_schedule(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    executor = Executor(None, "gpt-3.5-turbo")
    scheduler = Scheduler(db, executor)
    await scheduler.start()
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=20)).isoformat()
    schedule = {"schedule_type": "absolute", "datetime": future}
    schedule_str = parse_relative_time_to_cron(f"at {future}")
    task = Task(name="TestAbs", schedule=schedule_str, type=TaskType.REMINDER, reminder_message="msg")
    # Absolute schedule should raise ValueError when adding the task
    with pytest.raises(ValueError):
        await scheduler.add_task(task)
    await scheduler.stop()

@pytest.mark.asyncio
async def test_structured_recurrent_schedule(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    executor = Executor(None, "gpt-3.5-turbo")
    scheduler = Scheduler(db, executor)
    await scheduler.start()
    # Recurrent schedule: pass cron string directly
    cron = "0 9 * * 1"
    task = Task(name="TestRec", schedule=cron, type=TaskType.REMINDER, reminder_message="msg")
    t = await scheduler.add_task(task)
    assert t.schedule == cron
    assert t.next_run > datetime.datetime.now(datetime.timezone.utc)
    await scheduler.stop()
