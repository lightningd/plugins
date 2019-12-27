import os
from pyln.testing.fixtures import *  # noqa: F401,F403

plugin_path = os.path.join(os.path.dirname(__file__), "persistent-channels.py")


def test_persistent_channels_starts(node_factory):
    l1 = node_factory.get_node()
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()
