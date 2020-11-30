#!/usr/bin/env python3
from collections import namedtuple
from pyln.client import Plugin
from tqdm import tqdm
from typing import Mapping, Type, Iterator
from urllib.parse import urlparse
import json
import logging
import os
import struct
import sys
import sqlite3
import time
import psutil


plugin = Plugin()

root = logging.getLogger()
root.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)

# A change that was proposed by c-lightning that needs saving to the
# backup. `version` is the database version before the transaction was
# applied. The optional snapshot reqpresents a complete copy of the database,
# as it was before applying the `transaction`. This is used by the plugin from
# time to time to allow the backend to compress the changelog and forms a new
# basis for the backup.
Change = namedtuple('Change', ['version', 'snapshot', 'transaction'])


class Backend(object):
    def __init__(self, destination: str):
        """Read the metadata from the destination and prepare any necesary resources.

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
        """Set up any resources needed by this backend.

        """
        raise NotImplementedError

    def stream_changes(self) -> Iterator[Change]:
        """Retrieve changes from the backend in order to perform a restore.
        """
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

    def _db_open(self, dest: str) -> sqlite3.Connection:
        db = sqlite3.connect(dest)
        db.execute("PRAGMA foreign_keys = 1")
        return db

    def _restore_snapshot(self, snapshot: bytes, dest: str):
        if os.path.exists(dest):
            os.unlink(dest)
        with open(dest, 'wb') as f:
            f.write(snapshot)
        self.db = self._db_open(dest)

    def _restore_transaction(self, tx: Iterator[bytes]):
        assert(self.db)
        cur = self.db.cursor()
        for q in tx:
            cur.execute(q.decode('UTF-8'))
        self.db.commit()

    def restore(self, dest: str, remove_existing: bool = False):
        """Restore the backup in this backend to its former glory.

        If `dest` is a directory, we assume the default database filename:
        lightningd.sqlite3
        """
        if os.path.isdir(dest):
            dest = os.path.join(dest, "lightningd.sqlite3")
        if os.path.exists(dest):
            if not remove_existing:
                raise ValueError(
                    "Destination for backup restore exists: {dest}".format(
                        dest=dest
                    )
                )
            os.unlink(dest)

        self.db = self._db_open(dest)
        for c in tqdm(self.stream_changes()):
            if c.snapshot is not None:
                self._restore_snapshot(c.snapshot, dest)
            if c.transaction is not None:
                self._restore_transaction(c.transaction)


class FileBackend(Backend):
    def __init__(self, destination: str, create: bool):
        self.version = None
        self.prev_version = None
        self.destination = destination
        self.offsets = [0, 0]
        self.version_count = 0
        self.url = urlparse(self.destination)

        if os.path.exists(self.url.path) and create:
            raise ValueError("Attempted to create a FileBackend, but file already exists.")

    def initialize(self) -> bool:
        if not os.path.exists(self.url.path):
            self.version = 0
            self.prev_version = 0
            return False
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
            f.flush()

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
        with open(self.url.path, 'ab') as f:
            f.seek(self.offsets[0])
            f.write(length)
            f.write(version)
            f.write(typ)
            f.write(payload)
            self.prev_version, self.offsets[1] = self.version, self.offsets[0]
            self.version = entry.version
            self.offsets[0] += 9 + len(payload)
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
        with open(self.url.path, 'rb') as f:
            # Skip the header
            f.seek(512)
            while version < self.version:
                length, version, typ = struct.unpack("!IIb", f.read(9))
                payload = f.read(length)
                if typ == 1:
                    yield Change(version=version, snapshot=None, transaction=payload.split(b'\x00'))
                elif typ == 2:
                    yield Change(version=version, snapshot=payload, transaction=None)
                else:
                    raise ValueError("Unknown FileBackend entry type {}".format(typ))

            if version != self.version:
                raise ValueError("Versions do not match up: restored version {}, backend version {}".format(version, self.version))
            assert(version == self.version)



def resolve_backend_class(backend_url):
    backend_map: Mapping[str, Type[Backend]] = {
        'file': FileBackend,
    }
    p = urlparse(backend_url)
    backend_cl = backend_map.get(p.scheme, None)
    return backend_cl


def get_backend(destination, create=False, require_init=False):
    backend_cl = resolve_backend_class(destination)
    if backend_cl is None:
        raise ValueError("No backend implementation found for {destination}".format(
            destination=destination,
        ))
    backend = backend_cl(destination, create=create)
    initialized = backend.initialize()
    if require_init and not initialized:
        kill("Could not initialize the backup {}, please use 'backup-cli' to initialize the backup first.".format(destination))
    assert(backend.version is not None)
    assert(backend.prev_version is not None)
    return backend


def check_first_write(plugin, data_version):
    """Verify that we are up-to-date and c-lightning didn't forget writes.

    We may be at most 1 write off:

     - c-lightning and backup are at the same version (happy case)
     - c-lightning is 1 write behind: it must've crashed inbetween calling the
       hook and committing the DB transaction.
     - c-lightning is one or more writes ahead: either we lost some writes, or
       c-lightning was running without the plugin at some point -> crash!
     - c-lighning is more than 1 write behind: c-lightning had a lobotomy, or
       was restored from an old backup -> crash!
    """
    backend = plugin.backend

    logging.info("Comparing backup version {} versus first write version {}".format(
        backend.version, data_version
    ))

    if backend.version == data_version - 1:
        logging.info("Versions match up")
        return True

    elif backend.prev_version == data_version - 1 and plugin.backend.rewind():
        logging.info("Last changes not applied, rewinding non-committed transaction")
        return True

    elif backend.prev_version > data_version - 1:
        kill("c-lightning seems to have lost some state (failed restore?). Emergency shutdown.")

    else:
        kill("Backup is out of date, we cannot continue safely. Emergency shutdown.")


@plugin.hook('db_write')
def on_db_write(writes, data_version, plugin, **kwargs):
    change = Change(data_version, None, writes)
    if not plugin.initialized:
        assert(check_first_write(plugin, change.version))
        plugin.initialized = True

    if plugin.backend.add_change(change):
        return {"result": "continue"}
    else:
        kill("Could not append DB change to the backup. Need to shutdown!")


@plugin.init()
def on_init(options, **kwargs):
    dest = options.get('backup-destination', 'null')
    if dest != 'null':
        plugin.log(
            "The `--backup-destination` option is deprecated and will be "
            "removed in future versions of the backup plugin. Please remove "
            "it from your configuration. The destination is now determined by "
            "the `backup.lock` file in the lightning directory",
            level="warn"
        )

    configs = plugin.rpc.listconfigs()
    if not configs['wallet'].startswith('sqlite3'):
        kill("The backup plugin only works with the sqlite3 database.")


def kill(message: str):
    plugin.log(message)
    time.sleep(1)
    # Search for lightningd in my ancestor processes:
    procs = [p for p in psutil.Process(os.getpid()).parents()]
    for p in procs:
        if p.name() != 'lightningd':
            continue
        plugin.log("Killing process {name} ({pid})".format(
            name=p.name(),
            pid=p.pid
        ))
        p.kill()

    # Sleep forever, just in case the master doesn't die on us...
    while True:
        time.sleep(30)



plugin.add_option(
    'backup-destination', None,
    'UNUSED. Kept for backward compatibility only. Please update your configuration to remove this option.'
)


if __name__ == "__main__":
    # Did we perform the first write check?
    plugin.initialized = False
    if not os.path.exists("backup.lock"):
        kill("Could not find backup.lock in the lightning-dir")

    d = json.load(open("backup.lock", 'r'))
    destination = d['backend_url']
    plugin.backend = get_backend(destination, require_init=True)
    plugin.run()
