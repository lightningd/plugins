from pyln.testing.fixtures import *  # noqa: F401, F403
from pyln.testing.utils import wait_for
from pprint import pprint
import os


plugin = os.path.join(os.getcwd(), 'probe.py')


def test_simple_probe(node_factory):
    opts = [{'plugin': plugin}, {}, {'plugin': plugin}]
    l1, l2, l3 = node_factory.line_graph(3, opts=opts, announce_channels=True,
                                         wait_for_announce=True)

    # Wait for all channels to be known to l1
    wait_for(lambda: len(l1.rpc.listchannels()['channels']) == 4)

    # A probe with a tiny (10sat) amount in the correct direction should work
    p = l1.rpc.probe(l3.info['id'])
    assert(p['failcode'] == 16399)
    channels = p['route'].split(',')

    # If I tell you to exclude the channel between l1 and l2 you should fail
    # right away.
    p = l1.rpc.probe(node_id=l3.info['id'], excludes=[channels[0]])
    assert(p['failcode'] == -1)

    # A probe from l3 to l1 should fail on the first channel since it's in the
    # exhausted direction (l3 is the fundee not the funder)
    p = l3.rpc.probe(l1.info['id'])
    assert(p['failcode'] == 4103)

    # Stopping the last node and then probing for it should result in a 4103
    l3.stop()
    p = l1.rpc.probe(l3.info['id'])
    assert(p['failcode'] == 4103)
    assert(p['erring_channel'] == channels[1])
