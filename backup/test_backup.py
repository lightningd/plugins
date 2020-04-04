from pyln.testing.fixtures import *
from pyln.client import RpcError
import os
import pytest
import subprocess


plugin_dir = os.path.dirname(__file__)
plugin_path = os.path.join(plugin_dir, "backup.py")
cli_path = os.path.join(os.path.dirname(__file__), "backup-cli")


def test_start(node_factory, directory):
    bpath = os.path.join(directory, 'lightning-1', 'regtest')
    bdest = 'file://' + os.path.join(bpath, 'backup.dbak')
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", bpath, bdest])
    opts = {
        'plugin': plugin_path,
        'backup-destination': bdest,
        }
    l1 = node_factory.get_node(options=opts, cleandir=False)

    l1.daemon.wait_for_log(r'backup.py')

    # Restart the node a couple of times, to check that we can resume normally
    for i in range(5):
        l1.restart()
        l1.daemon.wait_for_log(r'Versions match up')


def test_start_no_init(node_factory, directory):
    """The plugin should refuse to start if we haven't initialized the backup
    """
    bpath = os.path.join(directory, 'lightning-1', 'regtest')
    bdest = 'file://' + os.path.join(bpath, 'backup.dbak')
    os.makedirs(bpath)
    opts = {
        'plugin': plugin_path,
        'backup-destination': bdest,
    }
    l1 = node_factory.get_node(
        options=opts, cleandir=False, may_fail=True, start=False
    )

    with pytest.raises(RpcError):
        # The way we detect a failure to start is when we attempt to connect
        # to the RPC.
        l1.start()
    assert(l1.daemon.is_in_log(
        r'Could not find backup.lock in the lightning-dir'
    ))


def test_tx_abort(node_factory, directory):
    """Simulate a crash between hook call and DB commit.

    We simulate this by updating the data_version var in the database before
    restarting the node. This desyncs the node from the backup, and restoring
    may not work (depending on which transaction was pretend-rolled-back), but
    continuing should work fine, since it can happen that we crash just
    inbetween the hook call and the DB transaction.

    """
    bpath = os.path.join(directory, 'lightning-1', 'regtest')
    bdest = 'file://' + os.path.join(bpath, 'backup.dbak')
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", bpath, bdest])
    opts = {
        'plugin': plugin_path,
        'backup-destination': bdest,
        }
    l1 = node_factory.get_node(options=opts, cleandir=False)
    l1.stop()

    print(l1.db.query("SELECT * FROM vars;"))

    # Now fudge the data_version:
    l1.db.execute("UPDATE vars SET intval = intval - 1 WHERE name = 'data_version'")

    print(l1.db.query("SELECT * FROM vars;"))

    l1.restart()
    l1.daemon.wait_for_log(r'Last changes not applied')


def test_failing_restore(node_factory, directory):
    """The node database is having memory loss, make sure we abort.

    We simulate a loss of transactions by manually resetting the data_version
    in the database back to n-2, which is non-recoverable.

    """
    bpath = os.path.join(directory, 'lightning-1', 'regtest')
    bdest = 'file://' + os.path.join(bpath, 'backup.dbak')
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", bpath, bdest])
    opts = {
        'plugin': plugin_path,
        'backup-destination': bdest,
        }
    l1 = node_factory.get_node(options=opts, cleandir=False)
    l1.stop()

    # Now fudge the data_version:
    l1.db.execute("UPDATE vars SET intval = intval - 2 WHERE name = 'data_version'")

    with pytest.raises(Exception):
        l1.start()

    assert(l1.daemon.is_in_log(r'lost some state') is not None)


def test_intermittent_backup(node_factory, directory):
    """Simulate intermittent use of the backup, or an old file backup.

    """
    bpath = os.path.join(directory, 'lightning-1', 'regtest')
    bdest = 'file://' + os.path.join(bpath, 'backup.dbak')
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", bpath, bdest])
    opts = {
        'plugin': plugin_path,
        'backup-destination': bdest,
        }
    l1 = node_factory.get_node(options=opts, cleandir=False)

    # Now start without the plugin. This should work fine.
    del l1.daemon.opts['plugin']
    del l1.daemon.opts['backup-destination']
    l1.restart()

    # Now restart adding the plugin again, and it should fail due to gaps in
    # the backup.
    l1.stop()
    with pytest.raises(Exception):
        l1.daemon.opts.update(opts)
        l1.start()

    assert(l1.daemon.is_in_log(r'Backup is out of date'))
