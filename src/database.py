"""Small SQLite repository with one-time import from the legacy JSON store."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            collection TEXT NOT NULL,
            record_key TEXT NOT NULL,
            position INTEGER NOT NULL,
            payload TEXT NOT NULL,
            PRIMARY KEY (collection, record_key),
            UNIQUE (collection, position)
        );
        CREATE TABLE IF NOT EXISTS settings (
            name TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        );
    """)
    return connection


def load_state(db_path: Path, legacy_json: Path, defaults: dict[str, Any]) -> dict[str, Any]:
    """Load typed top-level collections from SQLite, importing the JSON file once."""
    with _connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        setting_count = connection.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
        if count == 0 and setting_count == 0 and legacy_json.exists():
            try:
                legacy = json.loads(legacy_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                legacy = {}
            _write_state(connection, legacy)

        result: dict[str, Any] = {}
        for row in connection.execute("SELECT name, payload FROM settings"):
            result[row["name"]] = json.loads(row["payload"])
        for row in connection.execute(
            "SELECT collection, payload FROM records ORDER BY collection, position"
        ):
            result.setdefault(row["collection"], []).append(json.loads(row["payload"]))
        return result


def _write_state(connection: sqlite3.Connection, data: dict[str, Any]) -> None:
    connection.execute("DELETE FROM records")
    connection.execute("DELETE FROM settings")
    record_rows = []
    setting_rows = []
    for name, value in data.items():
        if isinstance(value, list):
            for position, item in enumerate(value):
                item_key = str(item.get("id", position)) if isinstance(item, dict) else str(position)
                record_rows.append((name, item_key, position,
                                    json.dumps(item, ensure_ascii=False)))
        else:
            setting_rows.append((name, json.dumps(value, ensure_ascii=False)))
    connection.executemany(
        "INSERT INTO records(collection, record_key, position, payload) VALUES (?, ?, ?, ?)",
        record_rows,
    )
    connection.executemany(
        "INSERT INTO settings(name, payload) VALUES (?, ?)", setting_rows,
    )


def save_state(db_path: Path, data: dict[str, Any]) -> None:
    """Replace the application state in one SQLite transaction."""
    with _connect(db_path) as connection:
        _write_state(connection, data)
