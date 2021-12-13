import os
from pyln.testing.fixtures import *  # noqa: F401,F403
import requests
from subprocess import check_output
import tempfile

plugin_path = os.path.join(os.path.dirname(__file__), "lnurlp.py")


def test_lnurlp_starts(node_factory):
    tempmeta = tempfile.NamedTemporaryFile()
    tempmeta.write(b'{"metadata":"justfortestingpurposes"}')
    tempmeta.seek(0)

    l1 = node_factory.get_node(options={"plugin": plugin_path, "lnurlp-meta-path": tempmeta.name})

    l1.daemon.logsearch_start = 0
    l1.daemon.wait_for_log(r'Starting server on port 8806')

    r = requests.get('http://localhost:8806/payRequest?amount=123')

    # check for hanging process if status_code = 500
    assert(r.status_code == 200)

    # returned valid  invoice?
    b = r.json()
    assert(b['pr'].startswith("lnbcrt123"))

    # test rate-limit
    for i in range(0,20):
        r = requests.get('http://localhost:8806/payRequest?amount=123')
    assert(r.status_code == 429)
    assert("429 Too Many Requests" in r.text )

    tempmeta.close()
