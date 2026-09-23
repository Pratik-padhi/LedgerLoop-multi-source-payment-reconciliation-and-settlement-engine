"""SQLite persistence for reconciliation snapshots and auditable actions."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


class ReconciliationStore:
    """A local, transaction-safe store; no financial decision logic lives here."""

    def __init__(self, database_path: str | Path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS reconciliation_runs (
                    run_id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    dataset TEXT NOT NULL,
                    summary_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reconciliation_results (
                    run_id INTEGER NOT NULL REFERENCES reconciliation_runs(run_id),
                    transaction_id TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, transaction_id)
                );
                CREATE TABLE IF NOT EXISTS action_audit (
                    audit_id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    transaction_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
            """)

            self._ensure_column(db, "reconciliation_runs", "status", "TEXT NOT NULL DEFAULT 'PENDING'")
            self._ensure_column(db, "reconciliation_runs", "source_files_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(db, "reconciliation_runs", "notes", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "action_audit", "run_id", "INTEGER NOT NULL DEFAULT 0")

            db.execute("""
                CREATE TABLE IF NOT EXISTS uploaded_datasets (
                    upload_id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL REFERENCES reconciliation_runs(run_id),
                    source_name TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    rows INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    def _ensure_column(self, db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = db.execute(f"PRAGMA table_info({table})").fetchall()
        if any(row[1] == column for row in columns):
            return
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def save_run(self, dataset: str, summary: Mapping, results: Iterable[Mapping], *, status: str = "COMPLETED", source_files: Iterable[str] | None = None, notes: str = "") -> int:
        """Persist a pipeline snapshot atomically and return its generated ID."""
        now = datetime.now(timezone.utc).isoformat()
        payload = list(results)
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO reconciliation_runs(created_at, dataset, status, summary_json, source_files_json, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (now, dataset, status, json.dumps(dict(summary), sort_keys=True, default=str), json.dumps(list(source_files or []), default=str), notes),
            )
            run_id = int(cursor.lastrowid)
            db.executemany(
                """INSERT INTO reconciliation_results(run_id, transaction_id, tier, status, result_json)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (run_id, item["transaction_id"], item["tier"], item["data"].get("status", "UNKNOWN"),
                     json.dumps(item["data"], sort_keys=True, default=str))
                    for item in payload
                ],
            )
        return run_id

    def latest_run(self) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM reconciliation_runs ORDER BY run_id DESC LIMIT 1").fetchone()
            if row is None:
                return None
            results = db.execute(
                "SELECT transaction_id, tier, status, result_json FROM reconciliation_results WHERE run_id = ? ORDER BY transaction_id",
                (row["run_id"],),
            ).fetchall()
        return {"run_id": row["run_id"], "created_at": row["created_at"], "dataset": row["dataset"],
                "status": row["status"], "source_files": json.loads(row["source_files_json"]),
                "summary": json.loads(row["summary_json"]),
                "results": [{"transaction_id": r["transaction_id"], "tier": r["tier"],
                             "status": r["status"], "data": json.loads(r["result_json"])} for r in results]}

    def audit(self, *, actor: str, action: str, transaction_id: str, outcome: str, details: Mapping | None = None, run_id: int | None = None) -> None:
        if not actor.strip():
            raise ValueError("actor is required for an auditable action")
        with self._connect() as db:
            db.execute(
                "INSERT INTO action_audit(created_at, actor, action, transaction_id, outcome, details_json, run_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), actor.strip(), action, transaction_id, outcome,
                 json.dumps(dict(details or {}), sort_keys=True, default=str), int(run_id or 0)),
            )

    def add_upload(self, *, run_id: int, source_name: str, filename: str, sha256: str, rows: int, status: str, details: Mapping | None = None) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO uploaded_datasets(run_id, source_name, filename, sha256, rows, status, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, source_name, filename, sha256, int(rows), status, json.dumps(dict(details or {}), default=str), datetime.now(timezone.utc).isoformat()),
            )

    def list_runs(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM reconciliation_runs ORDER BY run_id DESC").fetchall()
        return [
            {
                "run_id": row["run_id"],
                "created_at": row["created_at"],
                "dataset": row["dataset"],
                "status": row["status"],
                "source_files": json.loads(row["source_files_json"]),
                "summary": json.loads(row["summary_json"]),
                "notes": row["notes"],
            }
            for row in rows
        ]
