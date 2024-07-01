import os
from pyln.testing.fixtures import *  # noqa: F401,F403

plugin_path = os.path.join(os.path.dirname(__file__), "clearnet.py")


def test_clearnet_starts(node_factory):
    l1 = node_factory.get_node()
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()


def test_clearnet_runs(node_factory):
    pluginopt = {"plugin": plugin_path}
    l1, l2 = node_factory.line_graph(2, opts=pluginopt)
    l1.rpc.clearnet()
