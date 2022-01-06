import logging, os, struct
import shutil
import tempfile
from typing import Iterator
from urllib.parse import urlparse
import threading

from backend import Backend, Change


class FileBackend(Backend):
    def __init__(self, destination: str, create: bool):
        self.version = None
        self.prev_version = None
        self.destination = destination
        self.offsets = [0, 0]
        self.version_count = 0
        self.url = urlparse(self.destination)
        self.lock = threading.Lock()
        self.t = threading.Thread()
        self.stop_compact = False

        if os.path.exists(self.url.path) and create:
            raise ValueError("Attempted to create a FileBackend, but file {} already exists.".format(self.url.path))

        if not os.path.exists(self.url.path) and not create:
            raise ValueError("Attempted to open a FileBackend but file doesn't already exists, use `backup-cli init` to initialize it first.")
        if create:
            # Initialize a new backup file
            self.version, self.prev_version = 0, 0
            self.offsets = [512, 0]
            self.version_count = 0
            self.write_metadata()

    def initialize(self) -> bool:
        return self.read_metadata()

    def write_metadata(self):
        blob = struct.pack("!IIQIQQ", 0x01, self.version, self.offsets[0],
                           self.prev_version, self.offsets[1],
                           self.version_count)

        # Pad the header
        blob += b'\x00' * (512 - len(blob))
        mode = "rb+" if os.path.exists(self.url.path) else "wb+"

        with open(self.url.path, mode) as f:
            f.seek(0)
            f.write(blob)

    def read_metadata(self):
        with open(self.url.path, 'rb') as f:
            blob = f.read(512)
            if len(blob) != 512:
                logging.warn("Corrupt FileBackend header, expected 512 bytes, got {} bytes".format(len(blob)))
                return False

            file_version, = struct.unpack_from("!I", blob)
            if file_version != 1:
                logging.warn("Unknown FileBackend version {}".format(file_version))
                return False

            self.version, self.offsets[0], self.prev_version, self.offsets[1], self.version_count, = struct.unpack_from("!IQIQQ", blob, offset=4)

        return True

    def add_change(self, entry: Change) -> bool:
        typ = b'\x01' if entry.snapshot is None else b'\x02'
        if typ == b'\x01':
            payload = b'\x00'.join([t.encode('UTF-8') for t in entry.transaction])
        elif typ == b'\x02':
            payload = entry.snapshot

        length = struct.pack("!I", len(payload))
        version = struct.pack("!I", entry.version)
        with self.lock: # _compact_async threat has concurrent access
            with open(self.url.path, 'ab') as f:
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
        # After rewinding we set offsets[1] and prev_version to 0 (best effort
        # result). If either of these are set to 0 we have two consecutive
        # rewinds which cannot be safely done (we'd be rewinding more than the
        # one in-flight transaction).
        if self.offsets[1] == 0 or self.prev_version == 0:
            logging.warn("Cannot rewind multiple times.")
            return False

        self.version, self.offsets[0] = self.prev_version, self.offsets[1]
        self.prev_version, self.offsets[1] = 0, 0
        return True

    def stream_changes(self, stop_version=None, offset=None) -> Iterator[Change]:
        if stop_version is None:
            self.read_metadata()
            stop_version = self.version

        offset = 512 if offset is None else offset
        version = -1
        with open(self.url.path, 'rb') as f:
            # Skip the header
            f.seek(offset)
            while version < stop_version:
                length, version, typ = struct.unpack("!IIb", f.read(9))
                payload = f.read(length)
                if typ == 1:
                    yield Change(
                        version=version,
                        snapshot=None,
                        transaction=[t.decode('UTF-8') for t in payload.split(b'\x00')]
                    )
                elif typ == 2:
                    yield Change(version=version, snapshot=payload, transaction=None)
                else:
                    raise ValueError("Unknown FileBackend entry type {}".format(typ))

            if version != stop_version:
                raise ValueError("Versions do not match up: restored version {}, backend version {}".format(version, stop_version))


    def stats(self):
        return {'backupsize': os.stat(self.url.path).st_size,
                'version_count': self.version_count}


    def compact(self):
        # return something JSON serializable socketbackend (server) can pass
        try:
            if self.t.is_alive():
                return {"result": "compaction still in progress"}
            elif self.version_count == 2:
                return {"result": self.stats()}

            # Path of the backup clone that we're trying to build up. We
            # are trying to put this right next to the original backup, to
            # maximize the chances of both being on the same FS, which
            # makes the move below atomic.
            # FIXME: Use urllib.parse to compose clone_dest?
            clone_dest = self.destination + ".compacting"
            clone = FileBackend(clone_dest, create=True)

            self.t = threading.Thread(name='_compact_async', target=self._compact_async, args=(clone,))
            self.t.start()
            return {"result": "compaction started"}
        except Exception as e:
            logging.error(e) # handled exceptions are not logged
            return {"error": str(e)}


    def _compact_async(self, clone):
        """
        This method is thread safe but assumes other threads don't call `rewind`, which
        seems fair as normally rewind only happens on first write at startup.
        It blocks `add_change` briefly to read metadata, but later potentially
        longer when catching-up with changes (db writes) that happened while compacting.
        """
        stats = {}

        # Freeze our view of latest backup state.
        with self.lock:
            self.read_metadata()
            stop_ver = self.version
            stop_offset = self.offsets[1]   # keep for catch-up
            stats['before'] = self.stats()

        # Create temporary snapshot database.
        tmp = tempfile.TemporaryDirectory()
        snapshotpath = os.path.join(tmp.name, "lightningd.sqlite3")
        self.db = self._db_open(snapshotpath)

        logging.info("Starting compaction: stats={}".format(stats))

        # Apply all changes from current backup to the snapshot database, up-to
        # version = stop_ver-1, The last change (transaction) with version = stop_ver
        # is kept for later.
        for change in self.stream_changes(stop_version=stop_ver):
            if self.stop_compact:
                return clone.cleanup()

            if change.snapshot is not None:
                self._restore_snapshot(change.snapshot, snapshotpath)

            if change.version == stop_ver:
                break

            if change.transaction is not None:
                self._restore_transaction(change.transaction)
        self.db.commit()

        # If this assertion fails we are in a degenerate state: we
        # have less than two changes in the backup (starting
        # c-lightning alone produces 6 changes), and compacting an
        # almost empty backup is not useful.
        assert change.transaction is not None
        assert change.version == stop_ver

        # Create a new snapshot blob from snapshot database
        snapshot = Change(
            version=stop_ver - 1,
            snapshot=open(snapshotpath, 'rb').read(),
            transaction=None
        )

        logging.debug("Adding initial snapshot with {} bytes for version {}".format(len(snapshot.snapshot), snapshot.version))
        clone.add_change(snapshot)
        assert clone.version == stop_ver - 1

        logging.debug("Adding transaction for version {}".format(change.version))
        clone.add_change(change)
        assert clone.version == stop_ver
        assert clone.prev_version == stop_ver - 1

        # Just some extra sanity check, the main thread can only _add_ changes
        assert self.version >= clone.version
        assert self.prev_version >= clone.prev_version

        # Refresh view of latest state so our clone can catch-up, then atomically
        # move clone-->self, all while blocking on_db_write
        # FIXME: depending on the backlog, catch-up (blocking c-lightning) can still
        # take long, the critical section can probably be reduced.
        with self.lock:
            log = []
            # fast-forward to where we left cloning and add versions we missed while compacting
            for change in self.stream_changes(offset=stop_offset):
                if self.stop_compact:
                    return clone.cleanup()

                # stream_changes() expects to read at least one version, so we start
                # at stop_offset, but clone already has stop_ver so skip it
                if change.version == stop_ver:
                    continue

                clone.add_change(change) # up-to and _including_ latest version
                log.append(change.version)

            if len(log):
                logging.debug("Added transaction versions {} to {} that happened while compacting".format(log[0], log[-1]))

            stats['after'] = clone.stats()
            logging.info("Compaction completed: stats={}".format(stats))

            assert clone.version == self.version
            assert clone.prev_version == self.prev_version
            logging.debug("swapping backups")
            shutil.move(clone.url.path, self.url.path)

            # Re-initialize ourselves so we have the correct metadata
            self.read_metadata()


    def cleanup(self):
        os.remove(self.url.path)
        logging.debug("compaction aborted")


    def shutdown(self):
        if self.t.is_alive():
            self.stop_compact = True
            self.t.join()
