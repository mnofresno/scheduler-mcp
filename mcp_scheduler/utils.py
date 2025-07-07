"""
Utility functions for MCP Scheduler.
"""
import logging
import sys
from typing import Optional
from datetime import datetime, timedelta
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
    Parse a relative time expression and convert it to a cron expression.
    
    Examples:
        "in 15 seconds" -> cron for 15 seconds from now
        "in 1 minute" -> cron for 1 minute from now
        "in 2 hours" -> cron for 2 hours from now
        "in 1 day" -> cron for 1 day from now
        "15 seconds" -> cron for 15 seconds from now
        "1 minute" -> cron for 1 minute from now
        "2023-10-06T17:09:05.000Z" -> cron for specific datetime
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"=== PARSING RELATIVE TIME: '{relative_time}' ===")
    
    # First, try to parse as ISO timestamp
    try:
        from datetime import datetime
        import re
        
        # Check if it's an ISO timestamp
        iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z?$'
        if re.match(iso_pattern, relative_time):
            logger.info(f"Detected ISO timestamp: {relative_time}")
            # Parse the ISO timestamp
            if relative_time.endswith('Z'):
                target_time = datetime.fromisoformat(relative_time[:-1])
            else:
                target_time = datetime.fromisoformat(relative_time)
            
            # For specific timestamps, we need to use a different approach
            # since cron expressions don't handle specific dates well
            # We'll use a relative approach based on current time
            now = datetime.now()
            time_diff = target_time - now
            
            if time_diff.total_seconds() <= 0:
                # If the time has already passed, schedule for next occurrence
                # For now, just schedule for 1 minute from now
                target_time = now + timedelta(minutes=1)
            
            # Convert to cron expression: minute hour day month day_of_week (5 columns)
            # Use * for day and month to make it relative to current date
            cron_expr = f"{target_time.minute} {target_time.hour} * * *"
            logger.info(f"Generated cron expression from ISO: '{cron_expr}'")
            return cron_expr
    except Exception as e:
        logger.info(f"Not an ISO timestamp: {e}")
    
    # Remove "in " prefix if present
    time_str = relative_time.lower().strip()
    if time_str.startswith("in "):
        time_str = time_str[3:]
    
    logger.info(f"After removing 'in ' prefix: '{time_str}'")
    
    # Parse patterns like "15 seconds", "1 minute", "2 hours", "1 day"
    patterns = [
        (r"(\d+)\s*second", "seconds"),
        (r"(\d+)\s*minute", "minutes"), 
        (r"(\d+)\s*hour", "hours"),
        (r"(\d+)\s*day", "days"),
        # Spanish patterns
        (r"(\d+)\s*segundo", "seconds"),
        (r"(\d+)\s*minuto", "minutes"),
        (r"(\d+)\s*hora", "hours"),
        (r"(\d+)\s*día", "days"),
        (r"(\d+)\s*dia", "days")  # Without accent
    ]
    
    for pattern, unit in patterns:
        match = re.match(pattern, time_str)
        if match:
            amount = int(match.group(1))
            logger.info(f"Matched pattern '{pattern}' with amount={amount}, unit={unit}")
            now = datetime.now()
            
            if unit == "seconds":
                target_time = now + timedelta(seconds=amount)
            elif unit == "minutes":
                target_time = now + timedelta(minutes=amount)
            elif unit == "hours":
                target_time = now + timedelta(hours=amount)
            elif unit == "days":
                target_time = now + timedelta(days=amount)
            else:
                raise ValueError(f"Unsupported time unit: {unit}")
            
            # Convert to cron expression: minute hour day month day_of_week (5 columns)
            # Use * for day and month to make it relative to current date
            cron_expr = f"{target_time.minute} {target_time.hour} * * *"
            logger.info(f"Generated cron expression: '{cron_expr}'")
            return cron_expr
    
    # If no pattern matches, assume it's already a cron expression
    logger.info(f"No pattern matched, returning original: '{relative_time}'")
    return relative_time
