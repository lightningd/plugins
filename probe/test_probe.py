import unittest
import os
from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.testing.utils import DEVELOPER

plugin_path = os.path.join(os.path.dirname(__file__), "probe.py")


def test_probe_starts(node_factory):
    l1 = node_factory.get_node()
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()


@unittest.skipIf(not DEVELOPER, "Gossip is slow")
def test_probe(node_factory):
    l1, l2, l3, l4 = node_factory.line_graph(
        4,
        opts=[
            {'plugin': plugin_path},
            {},
            {},
            {}
        ],
        wait_for_announce=True
    )

    res = l1.rpc.probe(l4.info['id'])
    assert(res['destination'] == l4.info['id'])
    assert(res['failcode'] == 16399)


@unittest.skipIf(not DEVELOPER, "Gossip is slow")
def test_route_unreachable(node_factory):
    l1, l2, l3, l4 = node_factory.line_graph(
        4,
        opts=[
            {'plugin': plugin_path},
            {},
            {},
            {}
        ],
        wait_for_announce=True
    )

    l2.rpc.close(l3.info['id'])

    res = l1.rpc.probe(l4.info['id'])
    assert(res['destination'] == l4.info['id'])
    assert(res['failcode'] == 16394)
    route = res['route'].split(',')
    assert(route.index(res['erring_channel']) == 1)
