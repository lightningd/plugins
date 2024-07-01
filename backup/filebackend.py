import logging
import os
import struct
import shutil
import tempfile
from typing import Iterator
from urllib.parse import urlparse
from backend import Backend, Change


class FileBackend(Backend):
    def __init__(self, destination: str, create: bool):
        self.version = None
        self.prev_version = None
        self.destination = destination
        self.offsets = [0, 0]
        self.version_count = 0
        self.url = urlparse(self.destination)

        if os.path.exists(self.url.path) and create:
            raise ValueError(
                "Attempted to create a FileBackend, but file already exists."
            )
        if not os.path.exists(self.url.path) and not create:
            raise ValueError(
                "Attempted to open a FileBackend but file doesn't already exists, use `backup-cli init` to initialize it first."
            )
        if create:
            # Initialize a new backup file
            self.version, self.prev_version = 0, 0
            self.offsets = [512, 0]
            self.version_count = 0
            self.write_metadata()

    def initialize(self) -> bool:
        return self.read_metadata()

    def write_metadata(self):
        blob = struct.pack(
            "!IIQIQQ",
            0x01,
            self.version,
            self.offsets[0],
            self.prev_version,
            self.offsets[1],
            self.version_count,
        )

        # Pad the header
        blob += b"\x00" * (512 - len(blob))
        mode = "rb+" if os.path.exists(self.url.path) else "wb+"

        with open(self.url.path, mode) as f:
            f.seek(0)
            f.write(blob)
            f.flush()

    def read_metadata(self):
        with open(self.url.path, "rb") as f:
            blob = f.read(512)
            if len(blob) != 512:
                logging.warn(
                    "Corrupt FileBackend header, expected 512 bytes, got {} bytes".format(
                        len(blob)
                    )
                )
                return False

            (file_version,) = struct.unpack_from("!I", blob)
            if file_version != 1:
                logging.warn("Unknown FileBackend version {}".format(file_version))
                return False

            (
                self.version,
                self.offsets[0],
                self.prev_version,
                self.offsets[1],
                self.version_count,
            ) = struct.unpack_from("!IQIQQ", blob, offset=4)

        return True

    def add_change(self, entry: Change) -> bool:
        typ = b"\x01" if entry.snapshot is None else b"\x02"
        if typ == b"\x01":
            payload = b"\x00".join([t.encode("UTF-8") for t in entry.transaction])
        elif typ == b"\x02":
            payload = entry.snapshot

        length = struct.pack("!I", len(payload))
        version = struct.pack("!I", entry.version)
        with open(self.url.path, "ab") as f:
            f.seek(self.offsets[0])
            f.write(length)
            f.write(version)
            f.write(typ)
            f.write(payload)
            self.prev_version, self.offsets[1] = self.version, self.offsets[0]
            self.version = entry.version
            self.offsets[0] += 9 + len(payload)
            self.version_count += 1
        self.write_metadata()

        return True

    def rewind(self):
        # After rewinding we set offsets[0] and prev_version to 0 (best effort
        # result). If either of these are set to 0 we have two consecutive
        # rewinds which cannot be safely done (we'd be rewinding more than the
        # one in-flight transaction).
        if self.offsets[1] == 0 or self.prev_version == 0:
            logging.warn("Cannot rewind multiple times.")
            return False

        self.version, self.offsets[0] = self.prev_version, self.offsets[1]
        self.prev_version, self.offsets[1] = 0, 0
        return True

    def stream_changes(self) -> Iterator[Change]:
        self.read_metadata()
        version = -1
        with open(self.url.path, "rb") as f:
            # Skip the header
            f.seek(512)
            while version < self.version:
                length, version, typ = struct.unpack("!IIb", f.read(9))
                payload = f.read(length)
                if typ == 1:
                    yield Change(
                        version=version,
                        snapshot=None,
                        transaction=[t.decode("UTF-8") for t in payload.split(b"\x00")],
                    )
                elif typ == 2:
                    yield Change(version=version, snapshot=payload, transaction=None)
                else:
                    raise ValueError("Unknown FileBackend entry type {}".format(typ))

            if version != self.version:
                raise ValueError(
                    "Versions do not match up: restored version {}, backend version {}".format(
                        version, self.version
                    )
                )
            assert version == self.version

    def compact(self):
        stop = self.version  # Stop one version short of the head when compacting
        tmp = tempfile.TemporaryDirectory()
        backupdir, clonename = os.path.split(self.url.path)

        # Path of the backup clone that we're trying to build up. We
        # are trying to put this right next to the original backup, to
        # maximize the chances of both being on the same FS, which
        # makes the move below atomic.
        clonepath = os.path.join(backupdir, clonename + ".compacting")

        # Location we extract the snapshot to and then apply
        # incremental changes.
        snapshotpath = os.path.join(tmp.name, "lightningd.sqlite3")

        stats = {
            "before": {
                "backupsize": os.stat(self.url.path).st_size,
                "version_count": self.version_count,
            },
        }

        print("Starting compaction: stats={}".format(stats))
        self.db = self._db_open(snapshotpath)

        for change in self.stream_changes():
            if change.version == stop:
                break

            if change.snapshot is not None:
                self._restore_snapshot(change.snapshot, snapshotpath)

            if change.transaction is not None:
                self._restore_transaction(change.transaction)
        self.db.commit()

        # If this assertion fails we are in a degenerate state: we
        # have less than two changes in the backup (starting
        # Core-Lightning alone produces 6 changes), and compacting an
        # almost empty backup is not useful.
        assert change is not None

        # Remember `change`, it's the rewindable change we need to
        # stash on top of the new snapshot.
        clone = FileBackend(clonepath, create=True)
        clone.offsets = [512, 0]

        # We are about to add the snapshot n-1 on top of n-2 (init),
        # followed by the last change for n on top of
        # n-1. prev_version trails that by one.
        clone.version = change.version - 2
        clone.prev_version = clone.version - 1
        clone.version_count = 0
        clone.write_metadata()

        snapshot = Change(
            version=change.version - 1,
            snapshot=open(snapshotpath, "rb").read(),
            transaction=None,
        )
        print(
            "Adding intial snapshot with {} bytes for version {}".format(
                len(snapshot.snapshot), snapshot.version
            )
        )
        clone.add_change(snapshot)

        assert clone.version == change.version - 1
        assert clone.prev_version == change.version - 2
        clone.add_change(change)

        assert self.version == clone.version
        assert self.prev_version == clone.prev_version

        stats["after"] = {
            "version_count": clone.version_count,
            "backupsize": os.stat(clonepath).st_size,
        }

        print(
            "Compacted {} changes, saving {} bytes, swapping backups".format(
                stats["before"]["version_count"] - stats["after"]["version_count"],
                stats["before"]["backupsize"] - stats["after"]["backupsize"],
            )
        )
        shutil.move(clonepath, self.url.path)

        # Re-initialize ourselves so we have the correct metadata
        self.read_metadata()

        return stats
