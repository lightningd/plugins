import os
from pyln.testing.fixtures import *  # noqa: F401,F403
import unittest

CI = os.environ.get('CI') in ('True', 'true')

plugin_path = os.path.join(os.path.dirname(__file__), "autopilot.py")
plugin_opt = {'plugin': plugin_path}


def test_starts(node_factory):
    l1 = node_factory.get_node(allow_broken_log=True)
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()


@unittest.skipIf(CI, "Test autopilot is hanging on DNS request")
def test_main(node_factory):
    l1, l2 = node_factory.line_graph(2, wait_for_announce=True, opts=plugin_opt)
    # just call main function
    res = l1.rpc.autopilot_run_once(dryrun=True)
    l1.daemon.wait_for_log("I'd like to open [0-9]+ new channels with [0-9]+msat satoshis each")
