from croniter import croniter
from datetime import datetime, timedelta, UTC
from mcp_scheduler.utils import parse_relative_time_to_cron

def test_parse_relative_time_to_cron_seconds():
    cron_expr = parse_relative_time_to_cron("in 20 seconds")
    now = datetime.now(UTC)
    # Use croniter with second_at_beginning=True for 6-field cron
    next_run = croniter(cron_expr, now, second_at_beginning=True).get_next(datetime)
    delta = (next_run - now).total_seconds()
    assert 10 <= delta <= 30, f"Expected next run in 10-30s, got {delta}s (cron: {cron_expr}, now: {now}, next_run: {next_run})"

def test_parse_relative_time_to_cron_minutes():
    cron_expr = parse_relative_time_to_cron("in 2 minutes")
    now = datetime.now(UTC)
    # Use croniter with second_at_beginning=True for 6-field cron
    next_run = croniter(cron_expr, now, second_at_beginning=True).get_next(datetime)
    delta = (next_run - now).total_seconds()
    assert 60 <= delta <= 180, f"Expected next run in 1-3min, got {delta}s (cron: {cron_expr})"
