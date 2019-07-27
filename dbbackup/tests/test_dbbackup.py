from fixtures import *  # noqa: F401,F403
from flaky import flaky  # noqa: F401
from lightning import RpcError
from utils import DEVELOPER, wait_for

import os
import pytest
import re
import shutil
import signal
import time
import unittest


# Crashing or shutting-down a node raises unpredictable errors/exceptions, thus @flaky
@flaky
def test_dbbackup_init(node_factory, executor):
    """Test plugin init: option --db-backup-file present, correct path and check/compare existing backup"""

    # Option `--db-backup-file` missing, should error and shutdown after start
    # random_hsm=True so that our stored v102 database is valid
    l1 = node_factory.get_node(allow_broken_log=True, random_hsm=True, start=False,
                               options={'plugin': 'tests/dbbackup/dbbackup.py'})

    with pytest.raises(ConnectionResetError):
        l1.start()
    # wait_for_log only works on running daemon and ours is exiting with rpc.stop()
    time.sleep(3)
    assert l1.daemon.is_in_log(r'\*\*BROKEN\*\* plugin-dbbackup.py No db-backup-file specified', start=l1.daemon.logsearch_start)

    # Now with an invalid file path (a directory), should error and shutdown
    l1.daemon.opts['db-backup-file'] = node_factory.directory
    with pytest.raises(ConnectionResetError):
        l1.start()
    assert l1.daemon.is_in_log(r'\*\*BROKEN\*\* plugin-dbbackup.py Could not create db-backup-file', start=l1.daemon.logsearch_start)

    # Create proper backup
    backup = os.path.join(node_factory.directory, "lightningd.sqlite3-backup")
    l1.daemon.opts['db-backup-file'] = backup
    l1.start()
    assert l1.daemon.is_in_log('plugin-dbbackup.py Creating new db-backup-file: {}'.format(backup), start=l1.daemon.logsearch_start)
    assert l1.daemon.is_in_log(r'plugin-dbbackup.py Initialized', start=l1.daemon.logsearch_start)

    # Disable the plugin, restart and trigger db change so it will differ from the backup
    l1.stop()
    del l1.daemon.opts['plugin']
    del l1.daemon.opts['db-backup-file']
    l1.start()
    l1.rpc.newaddr()

    # Re-enable plugin and restart, should error and shutdown
    l1.stop()
    l1.daemon.opts['plugin'] = 'tests/dbbackup/dbbackup.py'
    l1.daemon.opts['db-backup-file'] = backup
    l1.start()

    needle = l1.daemon.logsearch_start
    db = os.path.join(l1.daemon.lightning_dir, "lightningd.sqlite3")
    time.sleep(2)
    assert l1.daemon.is_in_log(r'Found existing db-backup-file: {} comparing...'.format(backup, db), start=needle)
    assert l1.daemon.is_in_log(r'\*\*BROKEN\*\* plugin-dbbackup.py Existing db-backup-file differs from original database', start=needle)
    assert l1.daemon.is_in_log(r'UNUSUAL lightningd(.*): JSON-RPC shutdown', start=needle)


@unittest.skipIf(not DEVELOPER, "needs DEVELOPER=1")
def test_dbbackup_recover(node_factory, executor):
    """Tests db backup plugin, recover from an unfortunate loss of database."""

    # l3 is our unfortunate, may_reconnect=False prevents reconnect-attempts,
    # but incoming or manual connections still work
    db_backup = os.path.join(node_factory.directory, "l3_lightningd.sqlite3-backup")
    opts = [{'may_reconnect': True},
            {'may_reconnect': False, 'may_fail': True},
            {'may_reconnect': False, 'may_fail': True,
             'plugin': 'tests/dbbackup/dbbackup.py',
             'db-backup-file': db_backup,
             'disconnect': ['@WIRE_UPDATE_FULFILL_HTLC']}]

    # l3 looses its database with a beneficial HTLC in flight
    l1, l2, l3 = node_factory.line_graph(3, opts=opts, wait_for_announce=True)
    l1.wait_for_route(l3)

    phash = l3.rpc.invoice(123000, 'test_pay', 'description')['payment_hash']
    route = l1.rpc.getroute(l3.info['id'], 123000, 1)['route']
    l1.rpc.sendpay(route, phash)
    l3.daemon.wait_for_log('Peer transient failure in CHANNELD_NORMAL')

    # Crash l3 and replace its database with the backup, restart and reconnect
    # FIXME Make it dev-crash ?
    l3.daemon.kill()
    db_orig = os.path.join(l3.daemon.lightning_dir, 'lightningd.sqlite3')
    os.rename(db_backup, db_orig)
    l3.daemon.opts.pop('dev-disconnect')
    l3.daemon.opts.pop('dev-no-reconnect')
    assert l1.rpc.listsendpays(payment_hash=phash)['payments'][0]['status'] == 'pending'
    l3.start()
    l2.rpc.connect(l3.info['id'], 'localhost', l3.port)['id']
    wait_for(lambda: l1.rpc.listsendpays(payment_hash=phash)['payments'][0]['status'] == 'complete')

    # a HACK to get around `ValueError: 2 nodes had unexpected reconnections`
    l3.daemon.logs = [re.sub('Peer has reconnected', 'MODDED_PeerHasReconnected', l) for l in l3.daemon.logs]
    l2.daemon.logs = [re.sub('Peer has reconnected', 'MODDED_PeerHasReconnected', l) for l in l2.daemon.logs]

    # TODO: Can we come up with something harder?
    # Is option_data_loss_protect: doing anything?


def test_dbbackup_write_fail(node_factory, executor):
    """When the plugin cannot write to backup file for some reason"""

    backup = os.path.join(node_factory.directory, "lightningd.sqlite3-backup")
    l1 = node_factory.get_node(allow_broken_log=True,
                               options={'plugin': 'tests/dbbackup/dbbackup.py',
                                        'db-backup-file': backup})

    # rename backup file will cause db_write failure and crash lightningd
    os.rename(backup, backup + '_')
    with pytest.raises(RpcError):
        l1.rpc.newaddr()        # Trigger a (post-init) database change
    # cannot use wait_for_log because daemon is dying
    assert l1.daemon.is_in_log(r'\*\*BROKEN\*\* plugin-dbbackup.py Failed to write to backup:', start=l1.daemon.logsearch_start)

    # un-rename backup file and restart, also tests that failed write
    # was not committed-to in original database
    os.rename(backup + '_', backup)
    l1.start()
    l1.daemon.wait_for_logs([r'plugin-dbbackup.py Existing db-backup-file OK and successfully synced',
                             r'plugin-dbbackup.py Initialized'])


def test_dbbackup_migrate(node_factory, executor):
    """When migrating from an older database version"""

    # Create node with a copy of an old (v102) database and its backup
    backup = os.path.join(node_factory.directory, "lightningd.sqlite3-backup")
    l1 = node_factory.get_node(start=False,
                               options={'plugin': 'tests/dbbackup/dbbackup.py',
                                        'db-backup-file': backup})

    db = os.path.join(l1.daemon.lightning_dir, "lightningd.sqlite3")
    shutil.copy('tests/dbbackup/tests/lightningd-v102.sqlite3', db)
    shutil.copy('tests/dbbackup/tests/lightningd-v102.sqlite3-backup', backup)
    l1.start()
    # `Updating database...` happens before current log cursor
    assert l1.daemon.is_in_log(r'Updating database from version 102 to')
    l1.daemon.wait_for_log(r'Existing db-backup-file OK and successfully synced')


def test_dbbackup_plugin_kill(node_factory, executor):
    """When the plugin dies unexpectedly, lightningd dies also"""

    backup = os.path.join(node_factory.directory, "lightningd.sqlite3-backup")
    l1 = node_factory.get_node(may_fail=True, allow_broken_log=True,
                               options={'plugin': 'tests/dbbackup/dbbackup.py',
                                        'db-backup-file': backup})

    # kill the plugin, be a bit careful extracting pid from log
    logline = l1.daemon.is_in_log('plugin-manager started\(\d+\).*dbbackup.py')
    assert logline is not None
    pid = int(re.search(r'plugin-manager started\((\d+)\).*dbbackup.py', logline).group(1))
    os.kill(pid, signal.SIGTERM)
    time.sleep(2)
    assert l1.daemon.is_in_log(r'\*\*BROKEN\*\* .*')
