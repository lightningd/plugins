import subprocess
import unittest

from pyln.client import Plugin
from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.testing.utils import DEVELOPER

from summary_avail import *

pluginopt = {'plugin': os.path.join(os.path.dirname(__file__), "summary.py")}


# returns a test plugin stub
def get_stub():
    plugin = Plugin()
    plugin.avail_peerstate = {}
    plugin.avail_count     = 0
    plugin.avail_interval  = 60
    plugin.avail_window    = 3600
    return plugin


# tests the 72hr exponential availibility tracing
# tests base algo and peerstate tracing
def test_summary_avail_101():
    # given
    plugin = get_stub()
    rpcpeers = {
        'peers' : [
            { 'id' : '1', 'connected' : True },
            { 'id' : '2', 'connected' : False },
            { 'id' : '3', 'connected' : True },
        ]
    }

    # when
    for i in range(100):
        trace_availability(plugin, rpcpeers)

    # then
    assert(plugin.avail_peerstate['1']['avail'] == 1.0)
    assert(plugin.avail_peerstate['2']['avail'] == 0.0)
    assert(plugin.avail_peerstate['3']['avail'] == 1.0)
    assert(plugin.avail_peerstate['1']['connected'] == True)
    assert(plugin.avail_peerstate['2']['connected'] == False)
    assert(plugin.avail_peerstate['3']['connected'] == True)


# tests for 50% downtime
def test_summary_avail_50():
    # given
    plugin = get_stub()
    rpcpeers_on = {
        'peers' : [
            { 'id' : '1', 'connected' : True },
        ]
    }
    rpcpeers_off = {
        'peers' : [
            { 'id' : '1', 'connected' : False },
        ]
    }

    # when
    for i in range(30):
        trace_availability(plugin, rpcpeers_on)
    for i in range(30):
        trace_availability(plugin, rpcpeers_off)

    # then
    assert(round(plugin.avail_peerstate['1']['avail'], 3) == 0.5)


# tests for 2/3 downtime
def test_summary_avail_33():
    # given
    plugin = get_stub()
    rpcpeers_on = {
        'peers' : [
            { 'id' : '1', 'connected' : True },
        ]
    }
    rpcpeers_off = {
        'peers' : [
            { 'id' : '1', 'connected' : False },
        ]
    }

    # when
    for i in range(20):
        trace_availability(plugin, rpcpeers_on)
    for i in range(40):
        trace_availability(plugin, rpcpeers_off)

    # then
    assert(round(plugin.avail_peerstate['1']['avail'], 3) == 0.333)


# tests for 1/3 downtime
def test_summary_avail_66():
    # given
    plugin = get_stub()
    rpcpeers_on = {
        'peers' : [
            { 'id' : '1', 'connected' : True },
        ]
    }
    rpcpeers_off = {
        'peers' : [
            { 'id' : '1', 'connected' : False },
        ]
    }

    # when
    for i in range(40):
        trace_availability(plugin, rpcpeers_on)
    for i in range(20):
        trace_availability(plugin, rpcpeers_off)

    # then
    assert(round(plugin.avail_peerstate['1']['avail'], 3) == 0.667)


# checks the leading window is smaller if interval count is low
# when a node just started
def test_summary_avail_leadwin():
    # given
    plugin = get_stub()
    rpcpeers_on = {
        'peers' : [
            { 'id' : '1', 'connected' : True },
        ]
    }
    rpcpeers_off = {
        'peers' : [
            { 'id' : '1', 'connected' : False },
        ]
    }

    # when
    trace_availability(plugin, rpcpeers_on)
    trace_availability(plugin, rpcpeers_on)
    trace_availability(plugin, rpcpeers_off)

    # then
    assert(round(plugin.avail_peerstate['1']['avail'], 3) == 0.667)


def test_summary_start(node_factory):
    l1 = node_factory.get_node(options=pluginopt)
    s = l1.rpc.summary()

    expected = {
        'format-hint': 'simple',
        'network': 'REGTEST',
        'num_channels': 0,
        'num_connected': 0,
        'num_gossipers': 0,
        'num_utxos': 0,
        'warning_no_address': 'NO PUBLIC ADDRESSES'
    }

    for k, v in expected.items():
        assert(s[k] == v)


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
