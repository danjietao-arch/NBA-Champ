"""Local SQLite store for the hourly quote job.

The model snapshot is reused when no new 2026-27 result has been recorded.
A failed book fetch is stored as a failure and does not overwrite a price
from an earlier hour. The same hour is not written twice.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS model_snapshots (
    model_version TEXT NOT NULL,
    model_as_of TEXT NOT NULL,
    parameter_status TEXT NOT NULL,
    reused INTEGER NOT NULL,
    PRIMARY KEY (model_version, model_as_of)
);
CREATE TABLE IF NOT EXISTS market_quotes (
    as_of_hour TEXT NOT NULL,
    model_version TEXT NOT NULL,
    market_id TEXT NOT NULL,
    team_id INTEGER,
    bid REAL,
    ask REAL,
    mid REAL,
    spread REAL,
    quote_status TEXT NOT NULL,
    book_timestamp TEXT,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (as_of_hour, model_version, market_id)
);
CREATE TABLE IF NOT EXISTS job_status (
    as_of_hour TEXT NOT NULL PRIMARY KEY,
    status TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    return connection


def record_hour(connection: sqlite3.Connection, as_of_hour: str, document: dict, quotes: list[dict], fetched_at: str) -> str:
    """Insert this hour once. Returns 'inserted' or 'already_recorded'."""
    existing = connection.execute(
        "SELECT 1 FROM job_status WHERE as_of_hour = ?",
        (as_of_hour,),
    ).fetchone()
    if existing:
        return "already_recorded"
    connection.execute(
        """
        INSERT OR IGNORE INTO model_snapshots (model_version, model_as_of, parameter_status, reused)
        VALUES (?, ?, ?, 1)
        """,
        (document["model_version"], document["model_as_of"], document["parameter_status"]),
    )
    for quote in quotes:
        connection.execute(
            """
            INSERT INTO market_quotes (
                as_of_hour, model_version, market_id, team_id, bid, ask, mid, spread,
                quote_status, book_timestamp, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                as_of_hour,
                document["model_version"],
                quote["market_id"],
                quote.get("team_id"),
                quote.get("bid"),
                quote.get("ask"),
                quote.get("mid"),
                quote.get("spread"),
                quote["quote_status"],
                quote.get("book_timestamp"),
                fetched_at,
            ),
        )
    failed = [quote for quote in quotes if quote["quote_status"] != "valid"]
    status = "partial" if failed else "ok"
    detail = f"valid={len(quotes) - len(failed)} other={len(failed)}"
    connection.execute(
        "INSERT INTO job_status (as_of_hour, status, detail) VALUES (?, ?, ?)",
        (as_of_hour, status, detail),
    )
    connection.commit()
    return "inserted"
