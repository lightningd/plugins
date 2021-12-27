#!/usr/bin/env python3
from pyln.client import Plugin
import json
import logging
import os
import sys
import time
import psutil
import re
from packaging import version

from backend import Change
from backends import get_backend, FileBackend

plugin = Plugin()

# modify the root logger already set-up in Plugin()
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().handlers[0].setFormatter(logging.Formatter('%(message)s'))


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

    Note that `data_version` belongs to the not-yet-committed transaction and is
    one ahead of the version committed-to in c-lightning's database.
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


@plugin.async_method("backup-compact")
def compact(plugin, request, **kwargs):
    """Perform a backup compaction.

    Asynchronously restores the DB from the backup, initializes a new
    backup from the restored DB, and then swaps out the backup
    file. This can be used to reduce the backup file's size as well as
    speeding up an eventual recovery by rolling in the incremental
    changes into the snapshot.

    """
    # workaround for compatibility with socketbackend
    r = plugin.backend.compact()
    if "error" in r:
        request.set_exception(r["error"])
    else:
        request.set_result(r) # plugin requires for immediate return


    # IMPORTANT NOTE
    # Don't make RPC calls (or any other) that trigger the db_write hook, we
    # would deadlock as we cannot handle the hook simultaneous in a single threat.
    # See: https://github.com/lightningd/plugins/issues/209
    #configs = plugin.rpc.listconfigs()
    #if not configs['wallet'].startswith('sqlite3'):
    #    kill("The backup plugin only works with the sqlite3 database.")


# FIXME: Move into Plugin class and generalize for all decorators?
def setup_version(plugin):
    md = re.match(r'(v\d+\.\d+\.\d+(?:-\d+)?)(?:-g(\w+))?', plugin.lightning_version)
    plugin.ld_version = version.parse(md.group(1))

    if plugin.ld_version < version.parse('v0.9.2'):
        kill('requires lightningd v0.9.2 or higher')

    if plugin.ld_version >= version.parse('v0.10.2'):
        plugin.add_subscription("shutdown", handle_shutdown)


def handle_shutdown(plugin, **kwargs):
    # Cleanup a running compaction on a local FileBackend
    if isinstance(plugin.backend, FileBackend):
        plugin.backend.shutdown()

    # pre v0.10.2-126 had issue #4785, where we could miss db_write's made during
    # shutdown, then the safest is to wait and get killed by timeout.
    if plugin.ld_version < version.parse('v0.10.2-126'):
        plugin.log('with {}, we want to exit as last'.format(plugin.lightning_version))
    else:
        sys.exit(0)


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


if __name__ == "__main__":

    # We try to stay compatible with one year old releases
    setup_version(plugin)

    # Did we perform the first write check?
    plugin.initialized = False
    if not os.path.exists("backup.lock"):
        kill("Could not find backup.lock in the lightning-dir")

    try:
        d = json.load(open("backup.lock", 'r'))
        destination = d['backend_url']
        plugin.backend = get_backend(destination, require_init=True)
        plugin.run()
    except Exception:
        logging.exception('Exception while initializing backup plugin')
        kill('Exception while initializing plugin, terminating lightningd')
