import os
from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.testing.utils import wait_for, DEVELOPER, wait_channel_quiescent
import unittest


plugin_path = os.path.join(os.path.dirname(__file__), "rebalance.py")


def test_rebalance_starts(node_factory):
    l1 = node_factory.get_node()

    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()


@unittest.skipIf(not DEVELOPER, "Gossip is too slow")
def test_cycle(node_factory):
    l1, l2, l3, l4 = nodes = node_factory.line_graph(
        4, opts=[{'plugin': plugin_path}, {}, {}, {}]
    )

    l4.openchannel(l1, wait_for_announce=True)
    for n in nodes:
        wait_for(lambda: len(n.rpc.listchannels()['channels']) == 8)

    # Reach into RPC and enable notifications if available
    if hasattr(l1.rpc, "_notify"):
        def notify(**kwargs):
            print("Notification", kwargs)
        l1.rpc._notify = notify

    chans = [
        p['channels'][0]['short_channel_id']
        for p in l1.rpc.listpeers()['peers']
    ]
    l1.rpc.rebalance(*chans)

    wait_channel_quiescent(l1, l2)
    wait_channel_quiescent(l1, l4)

    balances = [
        p['channels'][0]['msatoshi_to_us']
        for p in l1.rpc.listpeers()['peers']
    ]

    from pprint import pprint
    pprint(balances)

    assert all([b > 0.49 * sum(balances) for b in balances])
