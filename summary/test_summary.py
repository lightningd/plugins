import subprocess
import unittest
import re
import os

from pyln.client import Plugin
from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.testing.utils import DEVELOPER, wait_for

from .summary_avail import trace_availability

pluginopt = {'plugin': os.path.join(os.path.dirname(__file__), "summary.py")}


# returns a test plugin stub
def get_stub():
    plugin = Plugin()
    plugin.avail_interval = 60
    plugin.avail_window = 3600
    plugin.persist = {}
    plugin.persist['p'] = {}
    plugin.persist['r'] = 0
    plugin.persist['v'] = 1
    return plugin


def test_summary_peer_thread(node_factory):
    # Set a low PeerThread interval so we can test quickly.
    opts = {'summary-availability-interval': 0.5}
    opts.update(pluginopt)
    l1, l2 = node_factory.line_graph(2, opts=opts)
    l2id = l2.info['id']

    # when
    s1 = l1.rpc.summary()
    l2.stop()  # we stop l2 and wait for l1 to see that
    l1.daemon.wait_for_log(f".*{l2id}.*Peer connection lost.*")
    wait_for(lambda: l1.rpc.listpeers(l2id)['peers'][0]['connected'] is False)
    l1.daemon.wait_for_log("Peerstate wrote to datastore")
    s2 = l1.rpc.summary()

    # then
    avail1 = int(re.search(' ([0-9]*)% ', s1['channels'][2]).group(1))
    avail2 = int(re.search(' ([0-9]*)% ', s2['channels'][2]).group(1))
    assert(avail1 == 100)
    assert(avail2 > 0 and avail2 < avail1)


# tests the 72hr exponential availibility tracing
# tests base algo and peerstate tracing
def test_summary_avail_101():
    # given
    plugin = get_stub()
    rpcpeers = {
        'peers': [
            {'id': '1', 'connected': True},
            {'id': '2', 'connected': False},
            {'id': '3', 'connected': True},
        ]
    }

    # when
    for i in range(100):
        trace_availability(plugin, rpcpeers)

    # then
    assert(plugin.persist['p']['1']['a'] == 1.0)
    assert(plugin.persist['p']['2']['a'] == 0.0)
    assert(plugin.persist['p']['3']['a'] == 1.0)
    assert(plugin.persist['p']['1']['c'] is True)
    assert(plugin.persist['p']['2']['c'] is False)
    assert(plugin.persist['p']['3']['c'] is True)


# tests for 50% downtime
def test_summary_avail_50():
    # given
    plugin = get_stub()
    rpcpeers_on = {
        'peers': [
            {'id': '1', 'connected': True},
        ]
    }
    rpcpeers_off = {
        'peers': [
            {'id': '1', 'connected': False},
        ]
    }

    # when
    for i in range(30):
        trace_availability(plugin, rpcpeers_on)
    for i in range(30):
        trace_availability(plugin, rpcpeers_off)

    # then
    assert(round(plugin.persist['p']['1']['a'], 3) == 0.5)


# tests for 2/3 downtime
def test_summary_avail_33():
    # given
    plugin = get_stub()
    rpcpeers_on = {
        'peers': [
            {'id': '1', 'connected': True},
        ]
    }
    rpcpeers_off = {
        'peers': [
            {'id': '1', 'connected': False},
        ]
    }

    # when
    for i in range(20):
        trace_availability(plugin, rpcpeers_on)
    for i in range(40):
        trace_availability(plugin, rpcpeers_off)

    # then
    assert(round(plugin.persist['p']['1']['a'], 3) == 0.333)


# tests for 1/3 downtime
def test_summary_avail_66():
    # given
    plugin = get_stub()
    rpcpeers_on = {
        'peers': [
            {'id': '1', 'connected': True},
        ]
    }
    rpcpeers_off = {
        'peers': [
            {'id': '1', 'connected': False},
        ]
    }

    # when
    for i in range(40):
        trace_availability(plugin, rpcpeers_on)
    for i in range(20):
        trace_availability(plugin, rpcpeers_off)

    # then
    assert(round(plugin.persist['p']['1']['a'], 3) == 0.667)


# checks the leading window is smaller if interval count is low
# when a node just started
def test_summary_avail_leadwin():
    # given
    plugin = get_stub()
    rpcpeers_on = {
        'peers': [
            {'id': '1', 'connected': True},
        ]
    }
    rpcpeers_off = {
        'peers': [
            {'id': '1', 'connected': False},
        ]
    }

    # when
    trace_availability(plugin, rpcpeers_on)
    trace_availability(plugin, rpcpeers_on)
    trace_availability(plugin, rpcpeers_off)

    # then
    assert(round(plugin.persist['p']['1']['a'], 3) == 0.667)


# checks whether the peerstate is persistent
def test_summary_persist(node_factory):
    # Set a low PeerThread interval so we can test quickly.
    opts = {'summary-availability-interval': 0.5, 'may_reconnect': True}
    opts.update(pluginopt)
    l1, l2 = node_factory.line_graph(2, opts=opts)

    # when
    l1.daemon.logsearch_start = 0
    l1.daemon.wait_for_log("Creating a new datastore")
    l1.daemon.wait_for_log("Peerstate wrote to datastore")
    s1 = l1.rpc.summary()
    l2.stop()
    l1.restart()
    assert l1.daemon.is_in_log("Reopened datastore")
    l1.daemon.logsearch_start = len(l1.daemon.logs)
    l1.daemon.wait_for_log("Peerstate wrote to datastore")
    s2 = l1.rpc.summary()

    # then
    avail1 = int(re.search(' ([0-9]*)% ', s1['channels'][2]).group(1))
    avail2 = int(re.search(' ([0-9]*)% ', s2['channels'][2]).group(1))
    assert(avail1 == 100)
    assert(0 < avail2 < 100)


def test_summary_start(node_factory):
    # given
    l1 = node_factory.get_node(options=pluginopt)
    l2 = node_factory.get_node(options=pluginopt)
    l1.connect(l2)

    # when
    s = l1.rpc.summary()

    # then
    expected = {
        'format-hint': 'simple',
        'network': 'REGTEST',
        'num_channels': 0,
        'num_connected': 0,
        'num_gossipers': 1,
        'num_utxos': 0,
        'warning_no_address': 'NO PUBLIC ADDRESSES'
    }
    for k, v in expected.items():
        assert(s[k] == v)


def test_summary_ascii(node_factory):
    # given
    l1, l2 = node_factory.line_graph(2, opts=pluginopt)
    l3, l5 = node_factory.line_graph(2, opts={**pluginopt, 'summary-ascii': None})

    # when
    s1 = l1.rpc.summary()
    s2 = l1.rpc.summary(ascii=True)
    s3 = l1.rpc.summary()  # remembers last calls ascii setting
    s4 = l1.rpc.summary(ascii=False)
    s5 = l1.rpc.summary()
    s6 = l3.rpc.summary()

    # then
    assert "├─────" in s1['channels'][-1]
    assert "[-----" in s2['channels'][-1]
    assert "[-----" in s3['channels'][-1]
    assert "├─────" in s4['channels'][-1]
    assert "├─────" in s5['channels'][-1]
    assert "[-----" in s6['channels'][-1]


def test_summary_opts(directory):
    opts = ['--summary-currency', '--summary-currency-prefix']

    help_out = subprocess.check_output([
        'lightningd',
        '--lightning-dir={}'.format(directory),
        '--help'
    ]).decode('utf-8')
    for o in opts:
        assert(o not in help_out)

    help_out = subprocess.check_output([
        'lightningd',
        '--lightning-dir={}'.format(directory),
        '--plugin={}'.format(pluginopt['plugin']),
        '--help'
    ]).decode('utf-8')
    for o in opts:
        assert(o in help_out)


@unittest.skipIf(not DEVELOPER, "We need fast gossip for line_graph")
def test_summary_exclude(node_factory):
    l1, l2 = node_factory.line_graph(2, opts=pluginopt)

    s = l1.rpc.summary()
    expected = {
        'format-hint': 'simple',
        'network': 'REGTEST',
        'num_channels': 1,
        'num_connected': 1,
        'num_gossipers': 0,
        'num_utxos': 1,
        'warning_no_address': 'NO PUBLIC ADDRESSES'
    }
    for k, v in expected.items():
        assert(s[k] == v)

    scid = l1.rpc.listchannels()['channels'][0]['short_channel_id']
    s = l1.rpc.summary(exclude=scid)
    expected = {
        'format-hint': 'simple',
        'network': 'REGTEST',
        'num_channels': 0,
        'num_connected': 0,
        'num_gossipers': 0,
        'num_utxos': 1,
        'warning_no_address': 'NO PUBLIC ADDRESSES'
    }
    for k, v in expected.items():
        assert(s[k] == v)
