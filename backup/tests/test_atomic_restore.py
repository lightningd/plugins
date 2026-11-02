import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import Backend, Change


class CaseBackend(Backend):
    def __init__(self, changes):
        self.changes = changes

    def stream_changes(self):
        yield from self.changes


def rows(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT value FROM samples ORDER BY value").fetchall()


def seeded(path, value):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE samples (value TEXT NOT NULL UNIQUE)")
        db.execute("INSERT INTO samples VALUES (?)", (value,))


def scratch_files(folder):
    return sorted(p.name for p in folder.iterdir())


def test_existing_destination_survives_failed_transaction(tmp_path):
    path = tmp_path / "lightningd.sqlite3"
    seeded(path, "existing")
    backend = CaseBackend([Change(1, None, ["CREATE TABLE samples (value TEXT UNIQUE)", "INSERT INTO nonexistent VALUES ('bad')"])])
    with pytest.raises(sqlite3.OperationalError):
        backend.restore(str(path), remove_existing=True)
    assert rows(path) == [("existing",)]
    assert scratch_files(tmp_path) == ["lightningd.sqlite3"]


def test_absent_destination_stays_absent_on_error(tmp_path):
    path = tmp_path / "restore.db"
    backend = CaseBackend([Change(1, None, ["CREATE TABLE samples (value TEXT UNIQUE)", "INSERT INTO nonexistent VALUES ('bad')"])])
    with pytest.raises(sqlite3.OperationalError):
        backend.restore(str(path))
    assert not path.exists()
    assert scratch_files(tmp_path) == []


def test_successful_replace_after_snapshot_then_transaction(tmp_path):
    path = tmp_path / "lightningd.sqlite3"
    snapshot = tmp_path / "snapshot.db"
    seeded(path, "existing")
    seeded(snapshot, "snapshot")
    data = snapshot.read_bytes()
    backend = CaseBackend([Change(1, data, ["INSERT INTO samples VALUES ('replayed')"])])
    backend.restore(str(path), remove_existing=True)
    assert rows(path) == [("replayed",), ("snapshot",)]
    assert scratch_files(tmp_path) == ["lightningd.sqlite3", "snapshot.db"]


def test_existing_destination_survives_stream_error_after_snapshot(tmp_path):
    path = tmp_path / "lightningd.sqlite3"
    snapshot = tmp_path / "snapshot.db"
    seeded(path, "existing")
    seeded(snapshot, "snapshot")
    backend = CaseBackend([Change(1, snapshot.read_bytes(), ["INSERT INTO samples VALUES ('next')", "BAD SYNTAX;"])])
    with pytest.raises(sqlite3.OperationalError):
        backend.restore(str(path), remove_existing=True)
    assert rows(path) == [("existing",)]
    assert scratch_files(tmp_path) == ["lightningd.sqlite3", "snapshot.db"]


def test_existing_destination_rejected_without_replace(tmp_path):
    path = tmp_path / "lightningd.sqlite3"
    seeded(path, "existing")
    with pytest.raises(ValueError, match="Destination for backup restore exists"):
        CaseBackend([]).restore(str(path))
    assert rows(path) == [("existing",)]
