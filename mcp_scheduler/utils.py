"""
Utility functions for MCP Scheduler.
"""
import logging
import sys
from typing import Optional
from datetime import datetime, timedelta, UTC
import re


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """Set up logging configuration."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(numeric_level)
    
    # Create formatters
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Add handlers
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # Clear existing handlers and add new ones
    logger.handlers = []
    for handler in handlers:
        logger.addHandler(handler)


def parse_cron_next_run(cron_expression: str, base_time: Optional[datetime] = None) -> datetime:
    """Parse a cron expression and return the next run time."""
    import croniter
    
    if base_time is None:
        base_time = datetime.utcnow()
    
    cron = croniter.croniter(cron_expression, base_time)
    return cron.get_next(datetime)


def format_duration(seconds: int) -> str:
    """Format duration in seconds to a human-readable string."""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    
    hours = minutes // 60
    minutes = minutes % 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} {minutes} minute{'s' if minutes != 1 else ''}"
    
    days = hours // 24
    hours = hours % 24
    return f"{days} day{'s' if days != 1 else ''} {hours} hour{'s' if hours != 1 else ''}"


def human_readable_cron(cron_expression: str) -> str:
    """Convert a cron expression to a human-readable string."""
    try:
        # This is a very basic implementation and could be expanded
        parts = cron_expression.split()
        
        if len(parts) < 5:
            return cron_expression
        
        seconds = parts[0] if len(parts) >= 6 else "0"
        minutes = parts[1] if len(parts) >= 6 else parts[0]
        hours = parts[2] if len(parts) >= 6 else parts[1]
        day_of_month = parts[3] if len(parts) >= 6 else parts[2]
        month = parts[4] if len(parts) >= 6 else parts[3]
        day_of_week = parts[5] if len(parts) >= 6 else parts[4]
        
        if seconds == "0" and minutes == "0" and hours == "0" and day_of_month == "*" and month == "*" and day_of_week == "*":
            return "Daily at midnight"
        
        if seconds == "0" and minutes == "0" and hours == "*" and day_of_month == "*" and month == "*" and day_of_week == "*":
            return "Every hour on the hour"
        
        if seconds == "0" and minutes == "*" and hours == "*" and day_of_month == "*" and month == "*" and day_of_week == "*":
            return "Every minute"
        
        # Default to returning the original expression
        return cron_expression
        
    except Exception:
        return cron_expression


def parse_relative_time_to_cron(relative_time: str) -> str:
    """
    Parse a relative time expression and convert it to a cron expression or delay string.
    - If < 60s: returns 'delay:N' (N=seconds)
    - If >= 60s: returns cron (5 fields, no seconds)
    - If ISO timestamp: returns cron (5 fields)
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"=== PARSING RELATIVE TIME: '{relative_time}' ===")

    from datetime import datetime, timedelta, UTC
    import re
    
    # Try ISO timestamp
    try:
        iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z?$'
        if re.match(iso_pattern, relative_time):
            logger.info(f"Detected ISO timestamp: {relative_time}")
            if relative_time.endswith('Z'):
                target_time = datetime.fromisoformat(relative_time[:-1])
            else:
                target_time = datetime.fromisoformat(relative_time)
            now = datetime.now(UTC)
            time_diff = target_time - now
            if time_diff.total_seconds() < 60:
                delay = max(1, int(time_diff.total_seconds()))
                logger.info(f"ISO time < 60s, using delay:{delay}")
                return f"delay:{delay}"
            # 5-field cron: min hour day month dow
            cron_expr = f"{target_time.minute} {target_time.hour} {target_time.day} {target_time.month} *"
            logger.info(f"Generated cron (from ISO): '{cron_expr}'")
            return cron_expr
    except Exception as e:
        logger.info(f"Not an ISO timestamp: {e}")

    # Relative time: 'in 20 seconds', '2 minutes', etc
    time_str = relative_time.lower().strip()
    if time_str.startswith("in "):
        time_str = time_str[3:]
    logger.info(f"After removing 'in ' prefix: '{time_str}'")
    patterns = [
        (r"(\d+)\s*second", "seconds"),
        (r"(\d+)\s*minute", "minutes"), 
        (r"(\d+)\s*hour", "hours"),
        (r"(\d+)\s*day", "days"),
        # The following patterns are for Spanish input compatibility. Remove or uncomment if multi-language support is needed.
        # (r"(\d+)\s*segundo", "seconds"),
        # (r"(\d+)\s*minuto", "minutes"),
        # (r"(\d+)\s*hora", "hours"),
        # (r"(\d+)\s*día", "days"),
        # (r"(\d+)\s*dia", "days")
    ]
    for pattern, unit in patterns:
        match = re.match(pattern, time_str)
        if match:
            amount = int(match.group(1))
            logger.info(f"Matched pattern '{pattern}' with amount={amount}, unit={unit}")
            now = datetime.now(UTC)
            if unit == "seconds":
                if amount < 60:
                    logger.info(f"Delay < 60s, using delay:{amount}")
                    return f"delay:{amount}"
                target_time = now + timedelta(seconds=amount)
            elif unit == "minutes":
                target_time = now + timedelta(minutes=amount)
            elif unit == "hours":
                target_time = now + timedelta(hours=amount)
            elif unit == "days":
                target_time = now + timedelta(days=amount)
            else:
                raise ValueError(f"Unsupported time unit: {unit}")
            # 5-field cron: min hour day month dow
            cron_expr = f"{target_time.minute} {target_time.hour} {target_time.day} {target_time.month} *"
            logger.info(f"Generated cron (relative): '{cron_expr}'")
            return cron_expr
    logger.info(f"No pattern matched, returning original: '{relative_time}'")
    return relative_time


def parse_structured_schedule(schedule):
    """
    Convert a structured schedule (dict) to a string schedule (delay:N or cron).
    Supports:
      - relative: {"schedule_type": "relative", "unit": "seconds"|"minutes"|"hours", "amount": N}
      - absolute: {"schedule_type": "absolute", "datetime": ISO8601}
      - recurrent: {"schedule_type": "recurrent", "cron": "..."}
    """
    if isinstance(schedule, dict):
        stype = schedule.get("schedule_type")
        if stype == "relative":
            unit = schedule.get("unit")
            amount = int(schedule.get("amount", 0))
            factor = {"seconds": 1, "minutes": 60, "hours": 3600}.get(unit, 1)
            delay_seconds = amount * factor
            return f"delay:{delay_seconds}"
        elif stype == "absolute":
            dt = schedule.get("datetime")
            from datetime import datetime, timezone
            target = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delay_seconds = int((target - now).total_seconds())
            if delay_seconds < 0:
                raise ValueError("Datetime is in the past")
            return f"delay:{delay_seconds}"
        elif stype == "recurrent":
            return schedule.get("cron")
        else:
            raise ValueError(f"Unknown schedule_type: {stype}")
    elif isinstance(schedule, str):
        return schedule
    else:
        raise ValueError("Invalid schedule format")
