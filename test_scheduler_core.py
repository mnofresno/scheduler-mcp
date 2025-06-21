import pytest
from mcp_scheduler.config import Config
from mcp_scheduler.executor import Executor
from mcp_scheduler.persistence import Database
from mcp_scheduler.scheduler import Scheduler
from mcp_scheduler.task import Task, TaskType
from mcp_scheduler.utils import parse_structured_schedule
import tempfile
import os
import asyncio
import datetime

@pytest.fixture
def temp_db():
    db_file = tempfile.NamedTemporaryFile(delete=False)
    db_file.close()
    yield db_file.name
    os.unlink(db_file.name)

@pytest.mark.asyncio
async def test_scheduler_add_and_list_tasks(temp_db):
    config = Config()
    db = Database(temp_db)
    executor = Executor(None, config.ai_model)
    scheduler = Scheduler(db, executor)
    await scheduler.start()
    task = Task(name="Test", schedule={"schedule_type": "recurrent", "cron": "* * * * *"}, type=TaskType.SHELL_COMMAND, command="echo hi")
    await scheduler.add_task(task)
    tasks = await scheduler.get_all_tasks()
    assert any(t.name == "Test" for t in tasks)
    await scheduler.stop()

@pytest.mark.asyncio
async def test_scheduler_run_task_now(temp_db):
    config = Config()
    db = Database(temp_db)
    executor = Executor(None, config.ai_model)
    scheduler = Scheduler(db, executor)
    await scheduler.start()
    task = Task(name="Test2", schedule={"schedule_type": "recurrent", "cron": "* * * * *"}, type=TaskType.SHELL_COMMAND, command="echo hi")
    t = await scheduler.add_task(task)
    execution = await scheduler.run_task_now(t.id)
    assert execution is not None
    await scheduler.stop()

@pytest.mark.asyncio
async def test_scheduler_enable_disable_task(temp_db):
    config = Config()
    db = Database(temp_db)
    executor = Executor(None, config.ai_model)
    scheduler = Scheduler(db, executor)
    await scheduler.start()
    task = Task(name="Test3", schedule={"schedule_type": "recurrent", "cron": "* * * * *"}, type=TaskType.SHELL_COMMAND, command="echo hi")
    t = await scheduler.add_task(task)
    await scheduler.disable_task(t.id)
    t2 = await scheduler.get_task(t.id)
    assert not t2.enabled
    await scheduler.enable_task(t.id)
    t3 = await scheduler.get_task(t.id)
    assert t3.enabled
    await scheduler.stop()

@pytest.mark.asyncio
async def test_scheduler_remove_task(temp_db):
    config = Config()
    db = Database(temp_db)
    executor = Executor(None, config.ai_model)
    scheduler = Scheduler(db, executor)
    await scheduler.start()
    task = Task(name="Test4", schedule={"schedule_type": "recurrent", "cron": "* * * * *"}, type=TaskType.SHELL_COMMAND, command="echo hi")
    t = await scheduler.add_task(task)
    await scheduler.delete_task(t.id)
    t2 = await scheduler.get_task(t.id)
    assert t2 is None
    await scheduler.stop()

@pytest.mark.asyncio
async def test_scheduler_relative_time_delay_seconds(temp_db):
    config = Config()
    db = Database(temp_db)
    executor = Executor(None, config.ai_model)
    scheduler = Scheduler(db, executor)
    await scheduler.start()
    # Usar formato estructurado
    schedule_struct = {"schedule_type": "relative", "unit": "seconds", "amount": 34}
    task = Task(name="TestDelay34s", schedule=schedule_struct, type=TaskType.REMINDER, reminder_message="Test message")
    t = await scheduler.add_task(task)
    # Debe guardar el dict estructurado
    assert t.schedule == schedule_struct
    # El parser debe devolver delay:34
    from mcp_scheduler.utils import parse_structured_schedule
    assert parse_structured_schedule(t.schedule) == "delay:34"
    # next_run debe ser ~34 segundos en el futuro
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = (t.next_run - now).total_seconds()
    assert 30 <= delta <= 36  # margen de error de 4s
    await scheduler.stop()
