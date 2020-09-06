import os
from pyln.testing.fixtures import *  # noqa: F401,F403


plugin_path = os.path.join(os.path.dirname(__file__), "fixroute.py")


def test_fixroute_starts(node_factory):
    l1 = node_factory.get_node(options={'plugin': plugin_path})

    # Ensure the plugin is still running:
    conf = l1.rpc.listconfigs()
    expected = [{
        'name': 'fixroute.py',
        'path': plugin_path
    }]
    assert(conf['plugins'] == expected)


def test_fixroute_dynamic_starts(node_factory):
    l1 = node_factory.get_node()
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    # Ensure the plugin is still running:
    conf = l1.rpc.listconfigs()
    expected = [{
        'name': 'fixroute.py',
        'path': plugin_path
    }]
    assert(conf['plugins'] == expected)
