#!/usr/bin/env python3
from pyln.client import Plugin
from pprint import pprint
from collections import namedtuple
from urllib.parse import urlparse
import struct
import os
from typing import Mapping, Type, Optional
import logging
import sys
from binascii import hexlify


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
# applied.
Change = namedtuple('Change',['version', 'transaction'])

class Backend(object):
    def __init__(self, destination: str):
        raise NotImplementedError

    def snapshot(self, filename: str) -> bool:
        raise NotImplementedError

    def add_change(self, change: Change) -> bool:
        raise NotImplementedError

    def initialize(self) -> bool:
        raise NotImplementedError

class FileBackend(Backend):
    def __init__(self, destination: str):
        self.version = None
        self.prev_version = None
        self.destination = destination
        self.offsets = [0, 0]
        self.version_count = 0
        self.url = urlparse(self.destination)

    def initialize(self) -> bool:
        if not os.path.exists(self.url.path):
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
            payload = b'\x00'.join([t.encode('ASCII') for t in entry.transaction])
        elif typ == b'\x02':
            payload = entry.snapshot

        length = struct.pack("!I", len(payload))
        with open(self.url.path, 'ab') as f:
            f.seek(self.offsets[0])
            f.write(length)
            f.write(payload)
            self.prev_version, self.offsets[1] = self.version, self.offsets[0]
            self.version = entry.version
            self.offsets[0] += 4 + len(payload)
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

backend_map: Mapping[str, Type[Backend]] = {
    'file': FileBackend,
}

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

    if backend.version  == data_version - 1:
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
    change = Change(data_version, writes)
    if not hasattr(plugin, 'backend'):
        plugin.early_writes.append(change)
        return True
    else:
        return apply_write(plugin, change)


def apply_write(plugin, change):
    if not plugin.initialized:
        assert(check_first_write(plugin, change.version))
        plugin.initialized = True

    return plugin.backend.add_entry(change)


@plugin.init()
def on_init(options: Mapping[str, str], plugin: Plugin, **kwargs):
    # Reach into the DB and
    configs = plugin.rpc.listconfigs()
    plugin.db_path = configs['wallet']
    destination = options['backup-destination']

    if not plugin.db_path.startswith('sqlite3'):
        abort("The backup plugin only works with the sqlite3 database.")

    if destination == 'null':
        abort("You must specify a backup destination, possibly on a secondary disk.")

    # Let's initialize the backed. First we need to figure out which backend to use.
    p = urlparse(destination)
    backend_cl = backend_map.get(p.scheme, None)
    if backend_cl is None:
        abort("Could not find a backend for scheme {p.scheme}".format(p=p))

    plugin.backend = backend_cl(destination)
    if not plugin.backend.initialize():
        abort("Could not initialize the backup {}, please use 'backup-cli' to initialize the backup first.".format(destination))

    for c in plugin.early_writes:
        apply_write(plugin, c)


plugin.add_option(
    'backup-destination', None,
    'Destination of the database backups (file:///filename/on/another/disk/).'
)


if __name__ == "__main__":
    # Did we perform the version check of backend versus the first write?
    plugin.initialized = False
    plugin.early_writes = []
    plugin.run()
