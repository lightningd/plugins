from collections import namedtuple
import os
import re
from typing import Iterator

import sqlite3
import tempfile

# A 'transaction' that was proposed by Core-Lightning and that needs saving to the
# backup. `version` is the `data_version` of the database **after** `transaction`
# has been applied. A 'snapshot' represents a complete copy of the database.
# This is used by the plugin from time to time to allow the backend to compress
# the changelog and forms a new basis for the backup.
# If `Change` contains a snapshot and a transaction, they apply in that order.
Change = namedtuple("Change", ["version", "snapshot", "transaction"])


class Backend(object):
    def __init__(self, destination: str):
        """Read the metadata from the destination and prepare any necessary resources.

        After this call the following members must be initialized:

         - backend.version: the last data version we wrote to the backend
         - backend.prev_version: the previous data version in case we need to
           roll back the last one
        """
        self.version = None
        self.prev_version = None
        raise NotImplementedError

    def add_change(self, change: Change) -> bool:
        """Add a single change to the backend.

        This call should always make sure that the change has been correctly
        written and flushed before returning.
        """
        raise NotImplementedError

    def initialize(self) -> bool:
        """Set up any resources needed by this backend."""
        raise NotImplementedError

    def stream_changes(self) -> Iterator[Change]:
        """Retrieve changes from the backend in order to perform a restore."""
        raise NotImplementedError

    def rewind(self) -> bool:
        """Remove the last change that was added to the backup

        Because the transaction is reported to the backup plugin before it is
        being committed to the database it can happen that we get notified
        about a transaction but then `lightningd` is stopped and the
        transaction is not committed. This means the backup includes an
        extraneous transaction which needs to be removed. A backend must allow
        a single rewind operation, and should fail additional calls to rewind
        (we may have at most one pending transaction not being committed at
        any time).

        """
        raise NotImplementedError

    def compact(self):
        """Apply some incremental changes to the snapshot to reduce our size."""
        raise NotImplementedError

    def _db_open(self, dest: str) -> sqlite3.Connection:
        db = sqlite3.connect(dest)
        db.execute("PRAGMA foreign_keys = 1")
        return db

    def _restore_snapshot(self, snapshot: bytes, dest: str):
        # Keep the private staging file and its permissions while replacing
        # the database image. Close SQLite before writing a raw snapshot.
        self.db.close()
        with open(dest, "r+b") as f:
            f.seek(0)
            f.truncate()
            f.write(snapshot)
        self.db = self._db_open(dest)

    def _rewrite_stmt(self, stmt: str) -> str:
        """We had a stmt expansion bug in Core-Lightning, this replicates the fix.

        We were expanding statements incorrectly, missing some
        whitespace between a param and the `WHERE` keyword. This
        re-inserts the space.

        """
        stmt = re.sub(r"reserved_til=([0-9]+)WHERE", r"reserved_til=\1 WHERE", stmt)
        stmt = re.sub(
            r"peer_id=([0-9]+)WHERE channels.id=",
            r"peer_id=\1 WHERE channels.id=",
            stmt,
        )
        return stmt

    def _restore_transaction(self, tx: Iterator[str]):
        assert self.db
        cur = self.db.cursor()
        for q in tx:
            q = self._rewrite_stmt(q)
            cur.execute(q)

    def restore(self, dest: str, remove_existing: bool = False):
        """Restore the backup in this backend to its former glory.

        If `dest` is a directory, we assume the default database filename:
        lightningd.sqlite3
        """
        if os.path.isdir(dest):
            dest = os.path.join(dest, "lightningd.sqlite3")
        if os.path.lexists(dest) and not remove_existing:
            raise ValueError(
                "Destination for backup restore exists: {dest}".format(dest=dest)
            )

        # Restore beside the target so the final rename stays on one filesystem.
        # Leave the previous database intact if reading or replaying fails.
        parent = os.path.dirname(os.path.abspath(dest))
        fd, staged = tempfile.mkstemp(
            prefix=".{name}.restore-".format(name=os.path.basename(dest)),
            dir=parent,
        )
        os.close(fd)
        self.db = None
        try:
            self.db = self._db_open(staged)
            for c in self.stream_changes():
                if c.snapshot is not None:
                    self._restore_snapshot(c.snapshot, staged)
                if c.transaction is not None:
                    self._restore_transaction(c.transaction)
            self.db.commit()
            self.db.close()
            self.db = None
            # Flush the complete image before making it the visible destination.
            with open(staged, "rb") as f:
                os.fsync(f.fileno())
            if os.path.lexists(dest) and not remove_existing:
                raise ValueError(
                    "Destination for backup restore exists: {dest}".format(dest=dest)
                )
            os.replace(staged, dest)
            staged = None
        finally:
            if self.db is not None:
                self.db.close()
                self.db = None
            if staged is not None and os.path.exists(staged):
                os.unlink(staged)
