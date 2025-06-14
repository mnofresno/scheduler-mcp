from mcp_scheduler.executor import Executor
import pytest
import asyncio

def test_executor_init():
    e = Executor()
    assert e.ai_model == "gpt-4o"

@pytest.mark.asyncio
async def test_executor_run_shell():
    e = Executor()
    output, error = await e.run_shell("echo hi")
    assert output.strip() == "hi"
    assert error is None
