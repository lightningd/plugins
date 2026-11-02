"""File-format recovery journeys; run directly with Python or with pytest.

Use real backup files, SQLite and independent reopened readers. No Lightning
process or funds are needed. Written against the unchanged source first.
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# In the repository this file lives in backup/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import Change
from filebackend import FileBackend


class RewindRestore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = self.root / 'source.sqlite3'
        with sqlite3.connect(source) as db:
            db.executescript("CREATE TABLE vars (name TEXT PRIMARY KEY, intval INTEGER);"
                             "INSERT INTO vars VALUES ('data_version',10);"
                             "CREATE TABLE entries (id INTEGER PRIMARY KEY, value TEXT);")
        self.url = (self.root / 'backup.bkp').as_uri()
        self.backend = FileBackend(self.url, create=True)
        self.backend.add_change(Change(10, source.read_bytes(), None))

    def add(self, version, *sql):
        writes = ["UPDATE vars SET intval={} WHERE name='data_version'".format(version)]
        self.assertTrue(self.backend.add_change(Change(version, None, writes + list(sql))))

    def reopen(self):
        backend = FileBackend(self.url, create=False)
        self.assertTrue(backend.initialize())
        return backend

    def restored_state(self):
        reader = self.reopen()
        dest = self.root / 'restored.sqlite3'
        try:
            reader.restore(str(dest))
        finally:
            if getattr(reader, 'db', None) is not None:
                reader.db.close()
        with sqlite3.connect(dest) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            version = db.execute("SELECT intval FROM vars WHERE name='data_version'").fetchone()[0]
            rows = db.execute('SELECT id,value FROM entries ORDER BY id').fetchall()
        return version, rows

    def test_normal_roundtrip(self):
        self.add(11, "INSERT INTO entries VALUES (1,'committed')")
        self.assertEqual(self.restored_state(), (11, [(1,'committed')]))

    def test_rewind_replacement_short_and_long(self):
        # A separate file for each length is essential: append-mode writes ignore
        # seek both when replacement is shorter and when it is longer.
        for text in ('new', 'new-' + 'x'*100):
            with self.subTest(value=text):
                source = self.root / 'source.sqlite3'
                self.url = (self.root / ('backup-'+str(len(text))+'.bkp')).as_uri()
                self.backend = FileBackend(self.url, create=True)
                self.backend.add_change(Change(10, source.read_bytes(), None))
                self.add(11, "INSERT INTO entries VALUES (1,'discarded')")
                self.assertTrue(self.backend.rewind())
                self.add(11, "INSERT INTO entries VALUES (2,'{}')".format(text))
                dest = self.root/'restored.sqlite3'
                if dest.exists():
                    dest.unlink()
                self.assertEqual(self.restored_state(), (11, [(2,text)]))

    def test_rewind_survives_reopen(self):
        self.add(11, "INSERT INTO entries VALUES (1,'discarded')")
        self.assertTrue(self.backend.rewind())
        self.backend = self.reopen()
        self.assertEqual(self.restored_state(), (10, []))
        self.assertFalse(self.backend.rewind())

    def test_replacement_after_reopen(self):
        self.add(11, "INSERT INTO entries VALUES (1,'discarded')")
        self.assertTrue(self.backend.rewind())
        self.backend = self.reopen()
        self.add(11, "INSERT INTO entries VALUES (2,'committed')")
        self.assertEqual(self.restored_state(), (11, [(2,'committed')]))

    def test_next_write_does_not_replay_discarded_transaction(self):
        self.add(11, "INSERT INTO entries VALUES (1,'discarded')")
        self.assertTrue(self.backend.rewind())
        self.add(11, "INSERT INTO entries VALUES (2,'committed')")
        self.add(12)
        self.assertEqual(self.restored_state(), (12, [(2,'committed')]))

    def test_reused_key_remains_restorable(self):
        self.add(11, "INSERT INTO entries VALUES (1,'discarded')")
        self.assertTrue(self.backend.rewind())
        self.add(11, "INSERT INTO entries VALUES (1,'committed')")
        self.add(12)
        self.assertEqual(self.restored_state(), (12, [(1,'committed')]))

    def test_compaction_retains_replacement(self):
        self.add(11, "INSERT INTO entries VALUES (1,'discarded')")
        self.assertTrue(self.backend.rewind())
        self.add(11, "INSERT INTO entries VALUES (2,'committed')")
        self.backend.compact()
        self.assertEqual(self.restored_state(), (11, [(2,'committed')]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
