import os
from pyln.testing.fixtures import *  # noqa: F401,F403
import requests
from prometheus_client import parser

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


def test_scrape_format(node_factory):
    l1, = node_factory.get_nodes(1, opts={'plugin': plugin_path})
    l1.daemon.wait_for_log(r'Prometheus plugin started')
    from pprint import pprint
    pprint(l1.rpc.listconfigs())

    scrape = requests.get("http://localhost:9900/metrics").content.decode('UTF-8')
    scrape = parser.text_string_to_metric_families(scrape)
    for i in scrape:
        pprint(i)
