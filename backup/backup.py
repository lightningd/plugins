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
import dropbox
import tempfile
import gnupg


TMP_BACKUP_NAME = "backup.dbak"

plugin = Plugin()

root = logging.getLogger()
root.setLevel(logging.DEBUG)

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
    def __init__(self, destination: str, options: Mapping[str, str],
                 create: bool):
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
        """

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

    def validate_options(self, options: Mapping[str, str]):
        raise NotImplementedError

class FileBackend(Backend):
    def __init__(self, destination: str, options: Mapping[str, str],
                 create: bool):
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

    def validate_options(self, options: Mapping[str, str]):
        pass

    def path_metadata(self):
        return self.url.path

    def path_current(self):
        return self.url.path

    def path_stream(self):
        return self.url.path

    def write_metadata(self):
        blob = struct.pack("!IIQIQQ", 0x01, self.version, self.offsets[0],
                           self.prev_version, self.offsets[1],
                           self.version_count)

        # Pad the header
        blob += b'\x00' * (512 - len(blob))
        mode = "rb+" if os.path.exists(self.path_metadata()) else "wb+"

        with open(self.path_metadata(), mode) as f:
            f.seek(0)
            f.write(blob)
            f.flush()

    def read_metadata(self):
        with open(self.path_metadata(), 'rb') as f:
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
        with open(self.path_current(), 'ab') as f:
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
        stop = self.offsets[0]
        with open(self.path_stream(), 'rb') as f:
            # Skip the header
            f.seek(512)
            while f.tell() < stop:
                length, version, typ = struct.unpack("!IIb", f.read(9))
                payload = f.read(length)
                if typ == 1:
                    yield Change(version=version, snapshot=None, transaction=payload.split(b'\x00'))
                elif typ == 2:
                    yield Change(version=version, snapshot=payload, transaction=None)
                else:
                    raise ValueError("Unknown FileBackend entry type {}".format(typ))

            assert(version == self.version)



class PartialFileBackend(FileBackend):
    def initialize(self) -> bool:
        if len(os.listdir(self.working_dir())) == 0:
            self.version = 0
            self.prev_version = 0
            return False
        return self.read_metadata()

    def working_dir(self):
        return os.path.dirname(self.url.path)

    def path_metadata(self):
        return "{}.0".format(self.url.path)

    def path_current(self):
        return "{}.{}".format(self.url.path, self.version)

    def path_stream(self):
        return self.url.path

    def stream_changes(self) -> Iterator[Change]:
        if os.path.exists(self.path_stream()):
            os.remove(self.path_stream())
        files = sorted(os.listdir(self.working_dir()),
                       key=lambda x: int(x.split(".")[-1]))
        with open(self.path_stream(), 'wb') as f:
            for partial in files:
                with open(os.path.join(self.working_dir(), partial), 'rb') as fp:
                    f.write(fp.read())
        return super().stream_changes()



class DropboxBackend(PartialFileBackend):
    def __init__(self, destination: str, options: Mapping[str, str],
                 create: bool):
        # Create a temporary directory in which the last downloaded backup will
        # be stored. Then use the FileBackend to operate on that file.
        self.tmpdir = tempfile.TemporaryDirectory(prefix="clightning-backup")
        super().__init__(destination, options, create)
        self.dropbox_url = urlparse(destination)
        self.dbx = dropbox.Dropbox(options["dropbox-token"])
        self.gpg = gnupg.GPG()
        self.pgp_key = None
        if options["pgp-key"] != "null":
            self.pgp_key = options["pgp-key"]

    def dropbox_dir(self):
        dd = os.path.dirname(self.url.path)
        # Dropbox API expects an empty string when accessing the main dir...
        if dd == "/":
            return ""
        return dd

    def dropbox_path(self, filename):
        # ..but it expects "/" when getting the file from the main dir...
        return os.path.join(os.path.dirname(self.url.path), filename)

    def working_dir(self):
        return self.tmpdir.name

    def base_filename(self):
        return os.path.basename(self.url.path)

    def path_metadata(self):
        return os.path.join(self.working_dir(),
                            "{}.0".format(self.base_filename()))

    def dropbox_path_metadata(self):
        return "{}.0".format(self.dropbox_url.path)

    def path_current(self):
        return os.path.join(self.working_dir(),
                            "{}.{}".format(self.base_filename(), self.version))

    def dropbox_path_current(self):
        return "{}.{}".format(self.dropbox_url.path, self.version)

    def path_stream(self):
        return os.path.join(self.working_dir(), self.base_filename())

    def decrypt_file(self, filename):
        with open(filename, 'rb') as f:
            # I would love to use gpg.decrypt_file as it seems to handle
            # buffering properly, but it's crashing on Python 3.8...
            content = self.gpg.decrypt(f.read()).data
        with open(filename, 'wb') as f:
            f.write(content)

    def encrypt_file(self, filename):
        with open(filename, 'rb') as f:
            content = f.read()
        with open(filename, 'wb') as f:
            f.write(self.gpg.encrypt(content, self.pgp_key).data)

    def initialize(self) -> bool:
        files = [f.name for f in
                 self.dbx.files_list_folder(self.dropbox_dir()).entries
                 if self.base_filename() in f.name]
        if len(files) == 0:
            self.version = 0
            self.prev_version = 0
            return False
        for f in files:
            self.dbx.files_download_to_file(os.path.join(self.working_dir(), f),
                                            self.dropbox_path(f))
        if self.pgp_key:
            for f in files:
                self.decrypt_file(os.path.join(self.working_dir(), f))
        return self.read_metadata()

    def validate_options(self, options: Mapping[str, str]):
        if options['dropbox-token'] == 'null':
            abort("You must specify access token for Dropbox")

    def write_metadata(self):
        super().write_metadata()
        if self.pgp_key:
            self.encrypt_file(self.path_metadata())
        with open(self.path_metadata(), 'rb') as f:
            self.dbx.files_upload(f.read(), self.dropbox_path_metadata(),
                                  mode=dropbox.files.WriteMode("overwrite"))

    def add_change(self, entry: Change) -> bool:
        # TODO(mrostecki): Handle the version bump properly.
        old_version = self.version
        res = super().add_change(entry)
        new_version = self.version
        self.version = old_version
        if self.pgp_key:
            self.encrypt_file(self.path_current())
        with open(self.path_current(), 'rb') as f:
            self.dbx.files_upload(f.read(), self.dropbox_path_current(),
                                  mode=dropbox.files.WriteMode("overwrite"))
        self.version = new_version
        return res


def resolve_backend_class(backend_url):
    backend_map: Mapping[str, Type[Backend]] = {
        'dropbox': DropboxBackend,
        'file': FileBackend,
        'partial': PartialFileBackend,
    }
    p = urlparse(backend_url)
    backend_cl = backend_map.get(p.scheme, None)
    return backend_cl


def get_backend(destination: str, options: Mapping[str, str],
                create=False, require_init=False):
    backend_cl = resolve_backend_class(destination)
    if backend_cl is None:
        raise ValueError("No backend implementation found for {destination}".format(
            destination=destination,
        ))
    backend = backend_cl(destination, options, create=create)
    backend.validate_options(options)
    initialized = backend.initialize()
    if require_init and not initialized:
        abort("Could not initialize the backup {}, please use 'backup-cli' to initialize the backup first.".format(destination))
    assert(backend.version is not None)
    assert(backend.prev_version is not None)
    return backend


def abort(reason: str) -> None:
    plugin.log(reason)
    plugin.rpc.stop()
    raise ValueError()


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
        abort("c-lightning seems to have lost some state (failed restore?). Emergency shutdown.")

    else:
        abort("Backup is out of date, we cannot continue safely. Emergency shutdown.")


@plugin.hook('db_write')
def on_db_write(writes, data_version, plugin, **kwargs):
    print(data_version, writes)
    change = Change(data_version, None, writes)
    if not hasattr(plugin, 'backend'):
        plugin.early_writes.append(change)
        return {"result": "continue"}
    else:
        return apply_write(plugin, change)


def apply_write(plugin, change):
    if not plugin.initialized:
        assert(check_first_write(plugin, change.version))
        plugin.initialized = True

    if plugin.backend.add_change(change):
        return {"result": "continue"}


@plugin.init()
def on_init(options: Mapping[str, str], plugin: Plugin, **kwargs):
    # Reach into the DB and
    configs = plugin.rpc.listconfigs()
    plugin.db_path = configs['wallet']
    destination = options['backup-destination']

    # Ensure that we don't inadventently switch the destination
    if not os.path.exists("backup.lock"):
        print("Files in the current directory {}".format(", ".join(os.listdir("."))))
        return abort("Could not find backup.lock in the lightning-dir, have you initialized using the backup-cli utility?")

    d = json.load(open("backup.lock", 'r'))
    if destination is None or destination == 'null':
        destination = d['backend_url']
    elif destination != d['backend_url']:
        abort(
            "The destination specified as option does not match the one "
            "specified in backup.lock. Please check your settings"
        )

    if not plugin.db_path.startswith('sqlite3'):
        abort("The backup plugin only works with the sqlite3 database.")

    plugin.backend = get_backend(destination, options, require_init=True)

    for c in plugin.early_writes:
        apply_write(plugin, c)


plugin.add_option(
    'backup-destination', None,
    'Destination of the database backups (file:///filename/on/another/disk/).'
)
plugin.add_option(
    'dropbox-token', os.environ.get('DROPBOX_TOKEN'),
    'Access token for Dropbox'
)
plugin.add_option(
    'pgp-key', None,
    'PGP key (ID or email) to encrypt the database backup'
)


if __name__ == "__main__":
    # Did we perform the version check of backend versus the first write?
    plugin.initialized = False
    plugin.early_writes = []
    plugin.run()
