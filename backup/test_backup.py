from flaky import flaky
from pyln.client import RpcError
from pyln.testing.fixtures import *
from pyln.client import RpcError
import os
import pytest
import subprocess


plugin_dir = os.path.dirname(__file__)
plugin_path = os.path.join(plugin_dir, "backup.py")
cli_path = os.path.join(os.path.dirname(__file__), "backup-cli")


class NodeFactoryWrapper(NodeFactory):
    def get_node(self, node_id=None, options=None, dbfile=None,
                 feerates=(15000, 11000, 7500, 3750), start=True,
                 wait_for_bitcoind_sync=True, expect_fail=False,
                 cleandir=True, **kwargs):

        node_id = self.get_node_id() if not node_id else node_id
        port = self.get_next_port()

        lightning_dir = os.path.join(
            self.directory, "lightning-{}/".format(node_id))

        if cleandir and os.path.exists(lightning_dir):
            shutil.rmtree(lightning_dir)

        # Get the DB backend DSN we should be using for this test and this
        # node.
        db = self.db_provider.get_db(os.path.join(lightning_dir, 'regtest'), self.testname, node_id)
        node = self.node_cls(
            node_id, lightning_dir, self.bitcoind, self.executor, db=db,
            port=port, options=options, **kwargs
        )

        # Regtest estimatefee are unusable, so override.
        node.set_feerates(feerates, False)

        self.nodes.append(node)
        if start:
            try:
                # Capture stderr if we're failing
                if expect_fail:
                    stderr = subprocess.PIPE
                else:
                    stderr = None
                node.start(wait_for_bitcoind_sync, stderr=stderr)
            except Exception:
                if expect_fail:
                    return node
                node.daemon.stop()
                raise
        return node


@pytest.fixture
def nf(request, directory, test_name, bitcoind, executor, db_provider, node_cls):
    """Temporarily patch the node_factory to not always clean the node directory.
    """
    nf = NodeFactoryWrapper(
        test_name,
        bitcoind,
        executor,
        directory=directory,
        db_provider=db_provider,
        node_cls=node_cls
    )

    yield nf
    ok, errs = nf.killall([not n.may_fail for n in nf.nodes])


def test_start(nf, directory):
    bpath = os.path.join(directory, 'lightning-1', 'regtest')
    bdest = 'file://' + os.path.join(bpath, 'backup.dbak')
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", bpath, bdest])
    opts = {
        'plugin': plugin_path,
        'backup-destination': bdest,
        }
    l1 = nf.get_node(options=opts, cleandir=False)

    l1.daemon.wait_for_log(r'backup.py')

    # Restart the node a couple of times, to check that we can resume normally
    for i in range(5):
        l1.restart()
        l1.daemon.wait_for_log(r'Versions match up')


def test_start_no_init(nf, directory):
    """The plugin should refuse to start if we haven't initialized the backup
    """
    bpath = os.path.join(directory, 'lightning-1', 'regtest')
    bdest = 'file://' + os.path.join(bpath, 'backup.dbak')
    os.makedirs(bpath)
    opts = {
        'plugin': plugin_path,
        'backup-destination': bdest,
    }
    l1 = nf.get_node(
        options=opts, cleandir=False, may_fail=True, start=False
    )

    with pytest.raises((RpcError, ConnectionRefusedError, ConnectionResetError)):
        # The way we detect a failure to start is when we attempt to connect
        # to the RPC.
        l1.start()
    assert(l1.daemon.is_in_log(
        r'Could not find backup.lock in the lightning-dir'
    ))


def test_init_not_empty(nf, directory):
    """We want to add backups to an existing lightning node.

    backup-cli init should start the backup with an initial snapshot.
    """
    bpath = os.path.join(directory, 'lightning-1', 'regtest')
    bdest = 'file://' + os.path.join(bpath, 'backup.dbak')
    l1 = nf.get_node()
    l1.stop()

    out = subprocess.check_output([cli_path, "init", bpath, bdest])
    assert(b'Found an existing database' in out)
    assert(b'Successfully written initial snapshot' in out)

    # Now restart and add the plugin
    l1.daemon.opts['plugin'] = plugin_path
    l1.start()
    l1.daemon.wait_for_log(r'plugin-backup.py: Versions match up')


def test_tx_abort(nf, directory):
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
    l1 = nf.get_node(options=opts, cleandir=False)
    l1.stop()

    print(l1.db.query("SELECT * FROM vars;"))

    # Now fudge the data_version:
    l1.db.execute("UPDATE vars SET intval = intval - 1 WHERE name = 'data_version'")

    print(l1.db.query("SELECT * FROM vars;"))

    l1.restart()
    l1.daemon.wait_for_log(r'Last changes not applied')


@flaky
def test_failing_restore(nf, directory):
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
    l1 = nf.get_node(options=opts, cleandir=False)
    l1.stop()

    # Now fudge the data_version:
    l1.db.execute("UPDATE vars SET intval = intval - 2 WHERE name = 'data_version'")

    with pytest.raises(Exception):
        l1.start()

    l1.daemon.proc.wait()
    assert(l1.daemon.is_in_log(r'lost some state') is not None)


def test_intermittent_backup(nf, directory):
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
    l1 = nf.get_node(options=opts, cleandir=False)

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

    l1.daemon.proc.wait()
    assert(l1.daemon.is_in_log(r'Backup is out of date') is not None)


def test_restore(nf, directory):
    bpath = os.path.join(directory, 'lightning-1', 'regtest')
    bdest = 'file://' + os.path.join(bpath, 'backup.dbak')
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", bpath, bdest])
    opts = {
        'plugin': plugin_path,
        'backup-destination': bdest,
        }
    l1 = nf.get_node(options=opts, cleandir=False)
    l1.stop()

    rdest = os.path.join(bpath, 'lightningd.sqlite.restore')
    subprocess.check_call([cli_path, "restore", bdest, rdest])
