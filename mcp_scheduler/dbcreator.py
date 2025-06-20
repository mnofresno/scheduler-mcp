import os
import sqlite3

DB_DIR = os.path.join(os.path.dirname(__file__), 'data')
DB_PATH = os.path.join(DB_DIR, 'scheduler.db')

tasks_table = '''
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    schedule TEXT NOT NULL,
    type TEXT NOT NULL,
    command TEXT,
    api_url TEXT,
    api_method TEXT,
    api_headers TEXT,
    api_body TEXT,
    prompt TEXT,
    description TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    do_only_once INTEGER NOT NULL DEFAULT 1,
    last_run TEXT,
    next_run TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reminder_title TEXT,
    reminder_message TEXT,
    client_request_id TEXT
);
'''

executions_table = '''
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    status TEXT,
    output TEXT,
    error TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);
'''

def ensure_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute(tasks_table)
        c.execute(executions_table)
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    ensure_db()
    print(f"Database and tables ensured at {DB_PATH}")
