from pyln.testing.fixtures import *

pluginopt = {'plugin': os.path.join(os.path.dirname(__file__), "summary.py")}


def test_summary_start(node_factory):
    l1 = node_factory.get_node(options=pluginopt)
    l1.rpc.getinfo()
