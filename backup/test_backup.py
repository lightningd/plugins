from backend import Backend
import socketbackend
from flaky import flaky
from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.testing.utils import sync_blockheight
import os
import pytest
import subprocess
import tempfile


plugin_dir = os.path.dirname(__file__)
plugin_path = os.path.join(plugin_dir, "backup.py")
cli_path = os.path.join(os.path.dirname(__file__), "backup-cli")

# For the transition period we require deprecated_apis to be true
deprecated_apis = True


def test_start(node_factory, directory):
    bpath = os.path.join(directory, "lightning-1", "regtest")
    bdest = "file://" + os.path.join(bpath, "backup.dbak")
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", "--lightning-dir", bpath, bdest])
    opts = {
        "plugin": plugin_path,
        "allow-deprecated-apis": deprecated_apis,
    }
    l1 = node_factory.get_node(options=opts, cleandir=False)
    plugins = [os.path.basename(p["name"]) for p in l1.rpc.plugin("list")["plugins"]]
    assert "backup.py" in plugins

    # Restart the node a couple of times, to check that we can resume normally
    for i in range(5):
        l1.restart()
        plugins = [
            os.path.basename(p["name"]) for p in l1.rpc.plugin("list")["plugins"]
        ]
        assert "backup.py" in plugins


def test_start_no_init(node_factory, directory):
    """The plugin should refuse to start if we haven't initialized the backup"""
    bpath = os.path.join(directory, "lightning-1", "regtest")
    os.makedirs(bpath)
    opts = {
        "plugin": plugin_path,
    }
    l1 = node_factory.get_node(options=opts, cleandir=False, may_fail=True, start=False)

    with pytest.raises(TimeoutError):
        # The way we detect a failure to start is when start() is running
        # into timeout looking for 'Server started with public key'.
        l1.start()
    assert l1.daemon.is_in_log(r"Could not find backup.lock in the lightning-dir")


def test_init_not_empty(node_factory, directory):
    """We want to add backups to an existing lightning node.

    backup-cli init should start the backup with an initial snapshot.
    """
    bpath = os.path.join(directory, "lightning-1", "regtest")
    bdest = "file://" + os.path.join(bpath, "backup.dbak")
    l1 = node_factory.get_node()
    l1.stop()

    out = subprocess.check_output([cli_path, "init", "--lightning-dir", bpath, bdest])
    assert b"Found an existing database" in out
    assert b"Successfully written initial snapshot" in out

    # Now restart and add the plugin
    l1.daemon.opts["plugin"] = plugin_path
    l1.daemon.opts["allow-deprecated-apis"] = deprecated_apis
    l1.start()
    assert l1.daemon.is_in_log(r"plugin-backup.py: Versions match up")


@flaky
def test_tx_abort(node_factory, directory):
    """Simulate a crash between hook call and DB commit.

    We simulate this by updating the data_version var in the database before
    restarting the node. This desyncs the node from the backup, and restoring
    may not work (depending on which transaction was pretend-rolled-back), but
    continuing should work fine, since it can happen that we crash just
    inbetween the hook call and the DB transaction.

    """
    bpath = os.path.join(directory, "lightning-1", "regtest")
    bdest = "file://" + os.path.join(bpath, "backup.dbak")
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", "--lightning-dir", bpath, bdest])
    opts = {
        "plugin": plugin_path,
        "allow-deprecated-apis": deprecated_apis,
    }
    l1 = node_factory.get_node(options=opts, cleandir=False)
    l1.stop()

    print(l1.db.query("SELECT * FROM vars;"))

    # Now fudge the data_version:
    l1.db.execute("UPDATE vars SET intval = intval - 1 WHERE name = 'data_version'")

    print(l1.db.query("SELECT * FROM vars;"))

    l1.restart()
    assert l1.daemon.is_in_log(r"Last changes not applied")


@flaky
def test_failing_restore(node_factory, directory):
    """The node database is having memory loss, make sure we abort.

    We simulate a loss of transactions by manually resetting the data_version
    in the database back to n-2, which is non-recoverable.

    """
    bpath = os.path.join(directory, "lightning-1", "regtest")
    bdest = "file://" + os.path.join(bpath, "backup.dbak")
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", "--lightning-dir", bpath, bdest])
    opts = {
        "plugin": plugin_path,
        "allow-deprecated-apis": deprecated_apis,
    }

    def section(comment):
        print("=" * 25, comment, "=" * 25)

    section("Starting node for the first time")
    l1 = node_factory.get_node(options=opts, cleandir=False, may_fail=True)
    l1.stop()

    # Now fudge the data_version:
    section("Simulating a restore of an old version")
    l1.db.execute("UPDATE vars SET intval = intval - 2 WHERE name = 'data_version'")

    section("Restarting node, should fail")
    with pytest.raises(Exception):
        l1.start()

    l1.daemon.proc.wait()
    section("Verifying the node died with an error")
    assert l1.daemon.is_in_log(r"lost some state") is not None


def test_intermittent_backup(node_factory, directory):
    """Simulate intermittent use of the backup, or an old file backup."""
    bpath = os.path.join(directory, "lightning-1", "regtest")
    bdest = "file://" + os.path.join(bpath, "backup.dbak")
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", "--lightning-dir", bpath, bdest])
    opts = {
        "plugin": plugin_path,
        "allow-deprecated-apis": deprecated_apis,
    }
    l1 = node_factory.get_node(options=opts, cleandir=False, may_fail=True)

    # Now start without the plugin. This should work fine.
    del l1.daemon.opts["plugin"]
    l1.restart()

    # Now restart adding the plugin again, and it should fail due to gaps in
    # the backup.
    l1.stop()
    with pytest.raises(Exception):
        l1.daemon.opts.update(opts)
        l1.start()

    l1.daemon.proc.wait()
    assert l1.daemon.is_in_log(r"Backup is out of date") is not None


def test_restore(node_factory, directory):
    bpath = os.path.join(directory, "lightning-1", "regtest")
    bdest = "file://" + os.path.join(bpath, "backup.dbak")
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", "--lightning-dir", bpath, bdest])
    opts = {
        "plugin": plugin_path,
        "allow-deprecated-apis": deprecated_apis,
    }
    l1 = node_factory.get_node(options=opts, cleandir=False)
    l1.stop()

    rdest = os.path.join(bpath, "lightningd.sqlite.restore")
    subprocess.check_call([cli_path, "restore", bdest, rdest])


def test_restore_dir(node_factory, directory):
    bpath = os.path.join(directory, "lightning-1", "regtest")
    bdest = "file://" + os.path.join(bpath, "backup.dbak")
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", "--lightning-dir", bpath, bdest])
    opts = {
        "plugin": plugin_path,
        "allow-deprecated-apis": deprecated_apis,
    }
    l1 = node_factory.get_node(options=opts, cleandir=False)
    l1.stop()

    # should raise error without remove_existing
    with pytest.raises(Exception):
        subprocess.check_call([cli_path, "restore", bdest, bpath])

    # but succeed when we remove the sqlite3 dbfile before
    os.remove(os.path.join(bpath, "lightningd.sqlite3"))
    subprocess.check_call([cli_path, "restore", bdest, bpath])


def test_warning(directory, node_factory):
    bpath = os.path.join(directory, "lightning-1", "regtest")
    bdest = "file://" + os.path.join(bpath, "backup.dbak")
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", "--lightning-dir", bpath, bdest])
    opts = {
        "plugin": plugin_path,
        "allow-deprecated-apis": deprecated_apis,
        "backup-destination": "somewhere/over/the/rainbox",
    }
    l1 = node_factory.get_node(options=opts, cleandir=False)
    l1.stop()

    assert l1.daemon.is_in_log(
        r"The `--backup-destination` option is deprecated and will be removed in future versions of the backup plugin."
    )


class DummyBackend(Backend):
    def __init__(self):
        pass


def test_rewrite():
    tests = [
        (
            r"UPDATE outputs SET status=123, reserved_til=1891733WHERE prev_out_tx=1 AND prev_out_index=2",
            r"UPDATE outputs SET status=123, reserved_til=1891733 WHERE prev_out_tx=1 AND prev_out_index=2",
        ),
    ]

    b = DummyBackend()

    for i, o in tests:
        assert b._rewrite_stmt(i) == o


def test_restore_pre_4090(directory):
    """The prev-4090-backup.dbak contains faulty expansions, fix em."""
    bdest = "file://" + os.path.join(
        os.path.dirname(__file__), "tests", "pre-4090-backup.dbak"
    )
    rdest = os.path.join(directory, "lightningd.sqlite.restore")
    subprocess.check_call([cli_path, "restore", bdest, rdest])


def test_compact(bitcoind, directory, node_factory):
    bpath = os.path.join(directory, "lightning-1", "regtest")
    bdest = "file://" + os.path.join(bpath, "backup.dbak")
    os.makedirs(bpath)
    subprocess.check_call([cli_path, "init", "--lightning-dir", bpath, bdest])
    opts = {
        "plugin": plugin_path,
        "allow-deprecated-apis": deprecated_apis,
    }
    l1 = node_factory.get_node(options=opts, cleandir=False)
    l1.rpc.backup_compact()

    tmp = tempfile.TemporaryDirectory()
    subprocess.check_call([cli_path, "restore", bdest, tmp.name])

    # Trigger a couple more changes and the compact again.
    bitcoind.generate_block(100)
    sync_blockheight(bitcoind, [l1])

    l1.rpc.backup_compact()
    tmp = tempfile.TemporaryDirectory()
    subprocess.check_call([cli_path, "restore", bdest, tmp.name])


def test_parse_socket_url():
    with pytest.raises(ValueError):
        # fail: invalid url scheme
        socketbackend.parse_socket_url("none")
        # fail: no port number
        socketbackend.parse_socket_url("socket:127.0.0.1")
        socketbackend.parse_socket_url("socket:127.0.0.1:")
        # fail: unbracketed IPv6
        socketbackend.parse_socket_url("socket:::1:1234")
        # fail: no port number IPv6
        socketbackend.parse_socket_url("socket:[::1]")
        socketbackend.parse_socket_url("socket:[::1]:")
        # fail: invalid port number
        socketbackend.parse_socket_url("socket:127.0.0.1:12bla")
        # fail: unrecognized query string key
        socketbackend.parse_socket_url("socket:127.0.0.1:1234?dummy=value")
        # fail: incomplete proxy spec
        socketbackend.parse_socket_url("socket:127.0.0.1:1234?proxy=socks5")
        socketbackend.parse_socket_url("socket:127.0.0.1:1234?proxy=socks5:")
        socketbackend.parse_socket_url("socket:127.0.0.1:1234?proxy=socks5:127.0.0.1:")
        # fail: unknown proxy scheme
        socketbackend.parse_socket_url(
            "socket:127.0.0.1:1234?proxy=socks6:127.0.0.1:9050"
        )

    # IPv4
    s = socketbackend.parse_socket_url("socket:127.0.0.1:1234")
    assert s.target.host == "127.0.0.1"
    assert s.target.port == 1234
    assert s.target.addrtype == socketbackend.AddrType.IPv4
    assert s.proxytype == socketbackend.ProxyType.DIRECT

    # IPv6
    s = socketbackend.parse_socket_url("socket:[::1]:1235")
    assert s.target.host == "::1"
    assert s.target.port == 1235
    assert s.target.addrtype == socketbackend.AddrType.IPv6
    assert s.proxytype == socketbackend.ProxyType.DIRECT

    # Hostname
    s = socketbackend.parse_socket_url("socket:backup.local:1236")
    assert s.target.host == "backup.local"
    assert s.target.port == 1236
    assert s.target.addrtype == socketbackend.AddrType.NAME
    assert s.proxytype == socketbackend.ProxyType.DIRECT

    # Tor
    s = socketbackend.parse_socket_url(
        "socket:backupserver.onion:1234?proxy=socks5:127.0.0.1:9050"
    )
    assert s.target.host == "backupserver.onion"
    assert s.target.port == 1234
    assert s.target.addrtype == socketbackend.AddrType.NAME
    assert s.proxytype == socketbackend.ProxyType.SOCKS5
    assert s.proxytarget.host == "127.0.0.1"
    assert s.proxytarget.port == 9050
    assert s.proxytarget.addrtype == socketbackend.AddrType.IPv4
