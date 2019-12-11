import subprocess
import unittest

from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.testing.utils import DEVELOPER

pluginopt = {'plugin': os.path.join(os.path.dirname(__file__), "summary.py")}


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
