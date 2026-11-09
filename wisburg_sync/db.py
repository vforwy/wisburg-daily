from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def checkpoint(conn: sqlite3.Connection, source: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM checkpoints WHERE source = ?",
        (source,),
    ).fetchone()


def existing_ids(conn: sqlite3.Connection, source: str) -> set[str]:
    rows = conn.execute(
        "SELECT remote_id FROM items WHERE source = ?",
        (source,),
    ).fetchall()
    return {row["remote_id"] for row in rows}


def upsert_item(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO items (
            source, remote_id, title, published_at, institution, body,
            list_json, detail_json, content_hash, first_seen_at,
            list_fetched_at, detail_fetched_at, updated_at, detail_status
        ) VALUES (
            :source, :remote_id, :title, :published_at, :institution, :body,
            :list_json, :detail_json, :content_hash, :first_seen_at,
            :list_fetched_at, :detail_fetched_at, :updated_at, :detail_status
        )
        ON CONFLICT (source, remote_id) DO UPDATE SET
            title = excluded.title,
            published_at = excluded.published_at,
            institution = excluded.institution,
            body = excluded.body,
            list_json = excluded.list_json,
            detail_json = excluded.detail_json,
            content_hash = excluded.content_hash,
            list_fetched_at = excluded.list_fetched_at,
            detail_fetched_at = excluded.detail_fetched_at,
            updated_at = excluded.updated_at,
            detail_status = excluded.detail_status
        """,
        row,
    )


def get_item(conn: sqlite3.Connection, source: str, remote_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM items WHERE source = ? AND remote_id = ?",
        (source, remote_id),
    ).fetchone()


def pending_details(conn: sqlite3.Connection, source: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT remote_id FROM items
        WHERE source = ? AND detail_status IN ('pending', 'error')
        ORDER BY published_at DESC
        """,
        (source,),
    ).fetchall()


def save_checkpoint(
    conn: sqlite3.Connection,
    *,
    source: str,
    latest_id: str | None,
    latest_published_at: str | None,
    last_success_at: str | None,
    last_status: str,
) -> None:
    conn.execute(
        """
        INSERT INTO checkpoints (
            source, latest_id, latest_published_at, last_success_at, last_status
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (source) DO UPDATE SET
            latest_id = excluded.latest_id,
            latest_published_at = excluded.latest_published_at,
            last_success_at = excluded.last_success_at,
            last_status = excluded.last_status
        """,
        (source, latest_id, latest_published_at, last_success_at, last_status),
    )


def start_run(conn: sqlite3.Connection, started_at: str, trigger: str) -> int:
    cursor = conn.execute(
        "INSERT INTO runs (started_at, trigger, status) VALUES (?, ?, 'running')",
        (started_at, trigger),
    )
    return int(cursor.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, finished_at: str, status: str) -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ? WHERE id = ?",
        (finished_at, status, run_id),
    )


def save_run_source(conn: sqlite3.Connection, run_id: int, stats: dict) -> None:
    conn.execute(
        """
        INSERT INTO run_sources (
            run_id, source, pages, listed, new_count, updated_count,
            detail_ok, detail_fail, status, error
        ) VALUES (
            :run_id, :source, :pages, :listed, :new_count, :updated_count,
            :detail_ok, :detail_fail, :status, :error
        )
        """,
        {"run_id": run_id, **stats},
    )
