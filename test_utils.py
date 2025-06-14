from mcp_scheduler.utils import format_duration, human_readable_cron

def test_format_duration():
    assert format_duration(65) == "1 minute"
    assert format_duration(3600) == "1 hour 0 minutes"
    assert format_duration(0) == "0 seconds"

def test_human_readable_cron():
    assert "Every minute" == human_readable_cron("* * * * *")
    assert "Daily at midnight" == human_readable_cron("0 0 * * *")
