import os
from pyln.testing.fixtures import *  # noqa: F401,F403

plugin_path = os.path.join(os.path.dirname(__file__), "donations.py")


def test_donation_starts(node_factory):
    l1 = node_factory.get_node()
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()


def test_donation_server(node_factory):
    pluginopt = {'plugin': plugin_path}
    l1, l2 = node_factory.line_graph(2, opts=pluginopt)
    l1.rpc.donationserver()
    l1.daemon.wait_for_logs('plugin-donations.py: Process server on port 8088')
    msg = l1.rpc.donationserver("stop")
    assert msg.startswith(f'stopped server on port 8088')
