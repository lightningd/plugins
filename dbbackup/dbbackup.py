#!/usr/bin/env python3
from lightning import Plugin
import os
import shutil
import sqlite3
from stat import S_IRUSR, S_IWUSR


plugin = Plugin()
plugin.sqlite_pre_init_cmds = []
plugin.initted = False


class NewBackupFileError(Exception):
    def __init__(self, path, e):
        self.message = 'Could not create db-backup-file {} : {}'.format(path, e)


# Create fresh backup, started as a copy
def new_backup_file(db, backup):
    try:
        shutil.copyfile(db, backup)
        os.chmod(backup, S_IRUSR | S_IWUSR)     # rw permission for owner
        plugin.log('Creating new db-backup-file: {}'.format(backup))
    except Exception as e:
        raise NewBackupFileError(backup, e)


@plugin.init()
def init(configuration, options, plugin):
    # FIXME: `==` should be changed to `is not None`, see workaround below
    if plugin.get_option('db-backup-file') == '':
        plugin.log('No db-backup-file specified', 'error')
        plugin.rpc.stop()   # stop lightningd

    try:
        db = os.path.join(configuration['lightning-dir'], 'lightningd.sqlite3')
        backup = plugin.get_option('db-backup-file')

        # If backup exist, replay pre_init_cmds on a temporary copy
        if os.path.isfile(backup):
            plugin.log('Found existing db-backup-file: {} comparing...'.format(backup))
            backup_copy = shutil.copy(backup, backup + '.tmp')
            db1 = sqlite3.connect(backup_copy, isolation_level=None)
            db2 = sqlite3.connect('file:{}?mode=ro'.format(db), uri=True)   # open in read-only
            for c in plugin.sqlite_pre_init_cmds:
                db1.execute(c)

            # If it then matches orignal db, replace backup with copy ... else abort
            dbs_match = [x for x in db1.iterdump()] == [x for x in db2.iterdump()]
            db1.close()
            db2.close()
            if dbs_match:
                os.rename(backup_copy, backup)
                plugin.log("Existing db-backup-file OK and successfully synced")
            else:
                plugin.log("Existing db-backup-file differs from original database, i.e. applying"
                           " pre-init statements (to a copy) didn't make it match the original db", 'error')
                os.remove(backup_copy)
                plugin.rpc.stop()   # stop lightningd

        else:
            new_backup_file(db, backup)

        plugin.conn = sqlite3.connect(backup, isolation_level=None)
        plugin.initted = True
        plugin.log('Initialized')
    except Exception as e:
        if isinstance(e, NewBackupFileError):
            plugin.log(e.message, 'error')
        else:
            plugin.log('Initialization failed: {}'.format(e), 'error')

        plugin.rpc.stop()   # stop lightningd


@plugin.hook('db_write')
def db_write(plugin, writes):
    if not plugin.initted:
        plugin.sqlite_pre_init_cmds += writes
    else:
        try:
            for c in writes:
                plugin.conn.execute(c)
        except Exception as e:
            plugin.log('Failed to write to backup: {}'.format(e), 'error')
            # This will `FATAL SIGNAL 6` crash lightningd, but it ensures the failed write
            # (here) to backup is also not committed-to in the original database
            return False

    return True


# Workaround for empty or absent option being (incorrectly?) passed as `null`
plugin.add_option('db-backup-file', '', 'The database backup file.')
plugin.run()
