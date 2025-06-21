# Structured Scheduling for MCP Scheduler

## Overview
This document describes the new structured scheduling system for the MCP Scheduler. Instead of relying on ambiguous string expressions (e.g., "in 34 seconds"), the scheduler now accepts a clear, extensible JSON format for all scheduling needs. This approach improves robustness, validation, and integration with LLMs and frontends.

---

## Supported Schedule Types

### 1. Relative (Delay)
- **Description:** Execute a task after a relative interval from now.
- **Example:** "in 34 seconds", "in 5 minutes"
- **JSON:**
```json
{
  "schedule_type": "relative",
  "unit": "seconds" | "minutes" | "hours",
  "amount": 34
}
```

### 2. Absolute (Specific Date/Time)
- **Description:** Execute a task at an exact date and time.
- **Example:** "2025-12-25T10:00:00Z"
- **JSON:**
```json
{
  "schedule_type": "absolute",
  "datetime": "2025-12-25T10:00:00Z"
}
```

### 3. Recurrent (Cron)
- **Description:** Execute a task periodically using a cron expression.
- **Example:** "Every Monday at 9:00"
- **JSON:**
```json
{
  "schedule_type": "recurrent",
  "cron": "0 9 * * 1"
}
```

---

## Extensible Types (for future use)
- **interval:** Every X time from creation
- **window:** Only within a time window
- **event:** Triggered by an external event

---

## Implementation Steps

1. **Define the JSON format** for all schedule types (see above).
2. **Implement a parser** (e.g., `parse_structured_schedule`) that converts the JSON into the internal format (e.g., `delay:N` or cron string).
3. **Update backend endpoints** to accept and validate the structured schedule JSON.
4. **Remove legacy string parsing** for natural language expressions.
5. **Add tests** for each schedule type to ensure correct behavior.
6. **Document the API** and provide examples for frontend/LLM integration.

---

## Example Payloads

### Relative
```json
{
  "name": "Drink water",
  "schedule": {
    "schedule_type": "relative",
    "unit": "minutes",
    "amount": 5
  },
  "type": "reminder"
}
```

### Absolute
```json
{
  "name": "Doctor appointment",
  "schedule": {
    "schedule_type": "absolute",
    "datetime": "2025-12-25T10:00:00Z"
  },
  "type": "reminder"
}
```

### Recurrent
```json
{
  "name": "Weekly report",
  "schedule": {
    "schedule_type": "recurrent",
    "cron": "0 9 * * 1"
  },
  "type": "reminder"
}
```

---

## Validation
- The backend must validate that the JSON contains all required fields for the given `schedule_type`.
- For `relative`, `unit` and `amount` are required.
- For `absolute`, `datetime` must be a valid ISO8601 string in the future.
- For `recurrent`, `cron` must be a valid cron expression.

---

## Migration Notes
- Legacy string schedules are still supported for backward compatibility, but new integrations should use the structured format.
- The parser can be easily extended to support new schedule types as needed.

---

## Benefits
- **Robustness:** No ambiguity or parsing errors.
- **Extensibility:** Easy to add new schedule types.
- **Validation:** Clear error messages for invalid input.
- **LLM/Frontend Friendly:** Simple to generate and consume.

---

## Next Steps
- Implement the parser and backend changes as described.
- Update tests and documentation.
- (Optional) Update frontend/LLM to generate structured schedule JSON.
