import os
from pyln.testing.fixtures import *  # noqa: F401,F403
from ephemeral_port_reserve import reserve  # type: ignore

plugin_path = os.path.join(os.path.dirname(__file__), "donations.py")


def test_donation_starts(node_factory):
    l1 = node_factory.get_node(allow_warning=True)
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()


def test_donation_server(node_factory):
    pluginopt = {"plugin": plugin_path, "donations-autostart": False}
    l1 = node_factory.get_node(options=pluginopt, allow_warning=True)
    port = reserve()
    l1.rpc.donationserver("start", port)
    l1.daemon.wait_for_log("plugin-donations.py:.*Serving Flask app 'donations'")
    l1.daemon.wait_for_log("plugin-donations.py:.*Running on all addresses")
    msg = l1.rpc.donationserver("stop", port)
    assert msg == f"stopped server on port {port}"
