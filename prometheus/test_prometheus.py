import os
from pyln.testing.fixtures import *  # noqa: F401,F403
import urllib
from ephemeral_port_reserve import reserve

plugin_path = os.path.join(os.path.dirname(__file__), "prometheus.py")


def test_prometheus_starts(node_factory):
    l1 = node_factory.get_node()
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()


def test_prometheus_scrape(node_factory):
    """Test that we can scrape correctly.
    """
    l1 = node_factory.get_node(options={'plugin': plugin_path})
    scrape = urllib.request.urlopen("http://localhost:9750")
    
    
    
def test_prometheus_channels(node_factory):
    port = reserve()
    l1, l2, l3 = node_factory.line_graph(
        3,
        opts=[
            {},
            {'plugin': plugin_path, 'prometheus-listen': f'127.0.0.1:{port}'},
            {}
        ]
    )
    scrape = urllib.request.urlopen(f'http://localhost:{port}')
    print(scrape)
