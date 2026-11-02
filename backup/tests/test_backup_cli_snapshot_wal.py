"""Initial backup-cli snapshot must include committed SQLite WAL transactions.

The writer exits without closing SQLite to leave the WAL on disk; this is a
real disposable SQLite recovery journey, not a mocked SQL transaction.
"""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
cli_path = Path(__file__).resolve().parents[1] / "backup-cli"
loader = importlib.machinery.SourceFileLoader("backup_cli_wal_test", str(cli_path))
spec = importlib.util.spec_from_loader(loader.name, loader)
backup_cli = importlib.util.module_from_spec(spec)
loader.exec_module(backup_cli)

WRITER = """
import os, sqlite3, sys
conn=sqlite3.connect(sys.argv[1])
conn.execute('CREATE TABLE vars (name TEXT PRIMARY KEY, intval INTEGER)')
conn.execute('CREATE TABLE entries (id INTEGER PRIMARY KEY, value TEXT)')
conn.execute("INSERT INTO vars VALUES ('data_version', 10)")
conn.commit()
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA wal_autocheckpoint=0')
conn.execute("UPDATE vars SET intval=11 WHERE name='data_version'")
conn.execute("INSERT INTO entries VALUES (1, 'committed_to_wal')")
conn.commit()
os._exit(0)
"""


def read_state(path):
    with sqlite3.connect(path) as db:
        version = db.execute(
            "SELECT intval FROM vars WHERE name='data_version'"
        ).fetchone()[0]
        rows = db.execute("SELECT id,value FROM entries ORDER BY id").fetchall()
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    return version, rows, integrity


def test_initial_snapshot_contains_wal_after_unclean_shutdown(tmp_path):
    db_path = tmp_path / "lightningd.sqlite3"
    subprocess.run(
        [sys.executable, "-c", WRITER, str(db_path)],
        check=True, timeout=10,
    )
    assert Path(str(db_path) + "-wal").exists()

    # Original backup-cli reads the version through SQLite, but copies only
    # the main file; prove the resulting mismatch before checking the repair.
    source = sqlite3.connect(db_path)
    actual_version = source.execute(
        "SELECT intval FROM vars WHERE name='data_version'"
    ).fetchone()[0]
    raw = tmp_path / "baseline.sqlite3"
    raw.write_bytes(db_path.read_bytes())
    assert actual_version == 11
    assert read_state(raw) == (10, [], "ok")

    version, snapshot = backup_cli.consistent_sqlite_snapshot(str(db_path))
    source.close()
    restored = tmp_path / "restored.sqlite3"
    restored.write_bytes(snapshot)
    assert version == 11
    assert read_state(restored) == (11, [(1, "committed_to_wal")], "ok")
