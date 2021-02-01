import os
from pyln.testing.fixtures import *  # noqa: F401,F403

plugin_path = os.path.join(os.path.dirname(__file__), "rebalance.py")
plugin_opt = {'plugin': plugin_path}


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


def test_rebalance_all(node_factory):
    l1, l2 = node_factory.line_graph(2, opts=plugin_opt)

    # for now just check we get an error if theres just one channel and we
    # could not perform an auto rebalance
    result = l1.rpc.rebalanceall()
    assert result['message'] == 'Error: Not enough open channels to balance anything'
