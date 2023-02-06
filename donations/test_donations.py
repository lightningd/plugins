import os
from pyln.testing.fixtures import *  # noqa: F401,F403
from ephemeral_port_reserve import reserve  # type: ignore
import time

plugin_path = os.path.join(os.path.dirname(__file__), "donations.py")


def test_donation_starts(node_factory):
    l1 = node_factory.get_node(allow_warning=True)
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    time.sleep(10)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()


def test_donation_server(node_factory):
    pluginopt = {'plugin': plugin_path, 'allow_warning': True}
    l1, l2 = node_factory.line_graph(2, opts=pluginopt)
    port = reserve()
    l1.rpc.donationserver('start', port)
    l1.daemon.wait_for_logs('plugin-donations.py: Process server on port')
    msg = l1.rpc.donationserver("stop", port)
    assert msg.startswith(f'stopped server on port')
