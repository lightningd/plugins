from pyln.testing.fixtures import *
import os
import subprocess


plugin = os.path.join(os.path.dirname(__file__), 'historian.py')


def test_start(node_factory):
    opts = {'plugin': plugin}
    l1 = node_factory.get_node(options=opts)
    l1.stop()

    help_out = subprocess.check_output([
        'lightningd',
        '--plugin={}'.format(plugin),
        '--lightning-dir={}'.format(l1.daemon.lightning_dir),
        '--help'
    ]).decode('utf-8').split('\n')
    help_out = [h.split('  ', 1) for h in help_out]
    help_out = [(v[0].strip(), v[1].strip()) for v in help_out if len(v) == 2]
    from pprint import pprint
    pprint(help_out)
