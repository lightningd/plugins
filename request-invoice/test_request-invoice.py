import os
from pyln.testing.fixtures import *  # noqa: F401,F403
import requests
from subprocess import check_output

plugin_path = os.path.join(os.path.dirname(__file__), "requestinvoice.py")


def test_requestinvoice_starts(node_factory):
    l1 = node_factory.get_node()
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()

    l1.daemon.logsearch_start = 0
    l1.daemon.wait_for_log(r'Starting server on port 8809')

    r = requests.get('http://localhost:8809/invoice/1000/text')

    # check for hanging process if status_code = 500
    assert(r.status_code == 200)

    # returned valid  invoice?
    b = r.json()
    assert(b['bolt11'][:8] == "lnbcrt10")


    # test rate-limit
    for i in range(0,20):
        r = requests.get('http://localhost:8809/invoice/1000/text')
    assert(r.status_code == 429)
    assert("429 Too Many Requests" in r.text )

    l1.rpc.plugin_stop(plugin_path)
    l1.stop()

    # terminate background process
    try:
        full_path = "python3 " + plugin_path
        check_output(["pkill","-f",  full_path])
    except:
        pass
