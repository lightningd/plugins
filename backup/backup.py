#!/usr/bin/env python3
from pyln.client import Plugin
import json
import logging
import os
import sys
import time
import psutil

from backend import Change
from backends import get_backend

plugin = Plugin()

root = logging.getLogger()
root.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(message)s")
handler.setFormatter(formatter)
root.addHandler(handler)


def check_first_write(plugin, data_version):
    """Verify that we are up-to-date and Core-Lightning didn't forget writes.

    We may be at most 1 write off:

     - Core-Lightning and backup are at the same version (happy case)
     - Core-Lightning is 1 write behind: it must've crashed inbetween calling the
       hook and committing the DB transaction.
     - Core-Lightning is one or more writes ahead: either we lost some writes, or
       Core-Lightning was running without the plugin at some point -> crash!
     - c-lighning is more than 1 write behind: Core-Lightning had a lobotomy, or
       was restored from an old backup -> crash!
    """
    backend = plugin.backend

    logging.info(
        "Comparing backup version {} versus first write version {}".format(
            backend.version, data_version
        )
    )

    if backend.version == data_version - 1:
        logging.info("Versions match up")
        return True

    elif backend.prev_version == data_version - 1 and plugin.backend.rewind():
        logging.info("Last changes not applied, rewinding non-committed transaction")
        return True

    elif backend.prev_version > data_version - 1:
        kill(
            "Core-Lightning seems to have lost some state (failed restore?). Emergency shutdown."
        )

    else:
        kill("Backup is out of date, we cannot continue safely. Emergency shutdown.")


@plugin.hook("db_write")
def on_db_write(writes, data_version, plugin, **kwargs):
    change = Change(data_version, None, writes)
    if not plugin.initialized:
        assert check_first_write(plugin, change.version)
        plugin.initialized = True

    if plugin.backend.add_change(change):
        return {"result": "continue"}
    else:
        kill("Could not append DB change to the backup. Need to shutdown!")


@plugin.method("backup-compact")
def compact(plugin):
    """Perform a backup compaction.

    Synchronously restores the DB from the backup, initializes a new
    backup from the restored DB, and then swaps out the backup
    file. This can be used to reduce the backup file's size as well as
    speeding up an eventual recovery by rolling in the incremental
    changes into the snapshot.

    """
    return plugin.backend.compact()


@plugin.init()
def on_init(options, **kwargs):
    dest = options.get("backup-destination", "null")
    if dest != "null":
        plugin.log(
            "The `--backup-destination` option is deprecated and will be "
            "removed in future versions of the backup plugin. Please remove "
            "it from your configuration. The destination is now determined by "
            "the `backup.lock` file in the lightning directory",
            level="warn",
        )

    # IMPORTANT NOTE
    # Putting RPC stuff in init() like the following can cause deadlocks!
    # See: https://github.com/lightningd/plugins/issues/209
    # configs = plugin.rpc.listconfigs()
    # if not configs['wallet'].startswith('sqlite3'):
    #     kill("The backup plugin only works with the sqlite3 database.")


def kill(message: str):
    plugin.log(message)
    time.sleep(1)
    # Search for lightningd in my ancestor processes:
    procs = [p for p in psutil.Process(os.getpid()).parents()]
    for p in procs:
        if p.name() != "lightningd":
            continue
        plugin.log("Killing process {name} ({pid})".format(name=p.name(), pid=p.pid))
        p.kill()

    # Sleep forever, just in case the master doesn't die on us...
    while True:
        time.sleep(30)


plugin.add_option(
    "backup-destination",
    None,
    "UNUSED. Kept for backward compatibility only. Please update your configuration to remove this option.",
)


if __name__ == "__main__":
    # Did we perform the first write check?
    plugin.initialized = False
    if not os.path.exists("backup.lock"):
        kill("Could not find backup.lock in the lightning-dir")

    try:
        d = json.load(open("backup.lock", "r"))
        destination = d["backend_url"]
        plugin.backend = get_backend(destination, require_init=True)
        plugin.run()
    except Exception:
        logging.exception("Exception while initializing backup plugin")
        kill("Exception while initializing plugin, terminating lightningd")
