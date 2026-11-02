"""Backup-record completeness acceptance cases from PROSPECTIVE_PLAN.md.

Run with `PYTHONPATH=./backup python -m pytest -q backup/test_incomplete_record.py`
from the repository root after placing this file in backup/. No real wallets.
"""
import sqlite3

import pytest

from backend import Change
from filebackend import FileBackend


def write_backup(tmp_path):
    backup_path = tmp_path / "backup.dbak"
    store = FileBackend(backup_path.as_uri(), create=True)
    assert store.add_change(
        Change(101, None, ["CREATE TABLE ledger (id TEXT PRIMARY KEY, sats INTEGER)"])
    )
    assert store.add_change(Change(102, None, ["INSERT INTO ledger VALUES ('a', 21000)"]))
    assert store.add_change(Change(103, None, ["DELETE FROM ledger WHERE id='missing'"]))
    reopened = FileBackend(backup_path.as_uri(), create=False)
    assert reopened.initialize() and reopened.version == 103
    return backup_path


def restore_and_read(path, dest):
    backend = FileBackend(path.as_uri(), create=False)
    assert backend.initialize()
    backend.restore(str(dest))
    with sqlite3.connect(dest) as db:
        rows = db.execute("SELECT id, sats FROM ledger ORDER BY id").fetchall()
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    return rows


def test_complete_record_and_old_trailing_bytes(tmp_path):
    path = write_backup(tmp_path)
    assert restore_and_read(path, tmp_path / "healthy.db") == [("a", 21000)]
    with path.open("ab") as f:
        f.write(b"OLD_TAIL_AFTER_KNOWN_VERSION")
    assert restore_and_read(path, tmp_path / "stale_tail.db") == [("a", 21000)]


@pytest.mark.parametrize("remaining", [b"DELETE FROM ledger", b""])
def test_truncated_backup_record_fails_before_silent_restore(tmp_path, remaining):
    path = write_backup(tmp_path)
    data = path.read_bytes()
    sql = b"DELETE FROM ledger WHERE id='missing'"
    assert data.count(sql) == 1
    pos = data.index(sql)
    path.write_bytes(data[:pos] + remaining)

    backend = FileBackend(path.as_uri(), create=False)
    assert backend.initialize() and backend.version == 103
    with pytest.raises(ValueError, match="Incomplete FileBackend record"):
        backend.restore(str(tmp_path / "incomplete.db"))
