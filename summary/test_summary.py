from pyln.testing.fixtures import *
import subprocess


pluginopt = {'plugin': os.path.join(os.path.dirname(__file__), "summary.py")}


def test_summary_start(node_factory):
    l1 = node_factory.get_node(options=pluginopt)
    s = l1.rpc.summary()
    from pprint import pprint;pprint(s)

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
