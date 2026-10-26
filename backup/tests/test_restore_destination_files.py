"""Normal recovery qualification of draft #1019 using disposable SQLite state."""
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import Change
from filebackend import FileBackend

CRASH_WRITER = '''
import os, sqlite3, sys
c=sqlite3.connect(sys.argv[1])
c.execute("PRAGMA journal_mode=WAL")
c.execute("PRAGMA wal_autocheckpoint=0")
c.execute("CREATE TABLE vars (name TEXT PRIMARY KEY, intval INTEGER)")
c.execute("CREATE TABLE samples (value TEXT UNIQUE)")
c.execute("INSERT INTO vars VALUES ('data_version', 50)")
c.execute("INSERT INTO samples VALUES ('old_destination')")
c.commit()
os._exit(0)
'''


def create_snapshot(path, mode):
    c = sqlite3.connect(str(path))
    c.execute('PRAGMA journal_mode=' + mode)
    c.execute('CREATE TABLE vars (name TEXT PRIMARY KEY, intval INTEGER)')
    c.execute('CREATE TABLE samples (value TEXT UNIQUE)')
    c.execute("INSERT INTO vars VALUES ('data_version', 100)")
    c.execute("INSERT INTO samples VALUES ('backup_snapshot')")
    c.commit()
    c.close()
    return path.read_bytes()


def read_state(path):
    c = sqlite3.connect(str(path))
    try:
        return {'rows': [r[0] for r in c.execute('SELECT value FROM samples ORDER BY value')],
                'version': c.execute("SELECT intval FROM vars WHERE name='data_version'").fetchone()[0],
                'integrity': c.execute('PRAGMA integrity_check').fetchone()[0]}
    finally:
        c.close()


def run(mode, destination):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        backup = FileBackend((root/'source.bkp').as_uri(), create=True)
        backup.add_change(Change(100, create_snapshot(root/'snapshot.db', mode), None))
        backup.add_change(Change(101, None, ["INSERT INTO samples VALUES ('committed')", "UPDATE vars SET intval=101 WHERE name='data_version'"]))
        target = root/'restored.db'
        if destination != 'clean':
            subprocess.run([sys.executable, '-c', CRASH_WRITER, str(target)], check=True, timeout=10)
            if not Path(str(target)+'-wal').exists():
                raise RuntimeError('setup did not retain a WAL')
            if destination == 'orphan_wal':
                target.unlink()
        before = {p.name:p.read_bytes() for p in root.glob('restored.db*')}
        caught = None
        try:
            reader = FileBackend((root/'source.bkp').as_uri(), create=False)
            reader.initialize()
            reader.restore(str(target), remove_existing=destination=='existing_wal')
        except Exception as e:
            caught={'type':type(e).__name__, 'message':str(e)}
        after = {p.name:p.read_bytes() for p in root.glob('restored.db*')}
        preserved = before == after
        restored = read_state(target) if target.exists() and not caught else None
        if destination == 'clean':
            accepted = caught is None and restored == {'rows':['backup_snapshot','committed'], 'version':101, 'integrity':'ok'}
        else:
            accepted = caught is not None and caught['type']=='ValueError' and preserved
        return {'snapshot_mode':mode,'destination':destination,'exception':caught,'destination_files_preserved':preserved,'restored':restored,'acceptance_pass':accepted,'leftover_stages':[p.name for p in root.glob('.*.restore-*')]}

@pytest.mark.parametrize("mode", ["DELETE", "WAL"])
@pytest.mark.parametrize("destination", ["clean", "existing_wal", "orphan_wal"])
def test_restore_keeps_destination_database_files_together(mode, destination):
    result = run(mode, destination)
    assert result["acceptance_pass"], result
    assert result["leftover_stages"] == []
