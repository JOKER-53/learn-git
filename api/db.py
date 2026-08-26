import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", "/dbdata/progress.db")

def get_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            reg_no TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            user_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            completed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, task_id)
        )
    """)
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "recovery_code_hash" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN recovery_code_hash TEXT")
    if "last_seen" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN last_seen TEXT")
    conn.commit()
    return conn
