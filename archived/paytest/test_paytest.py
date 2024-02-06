from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.client import RpcError
import os
import pytest
from pprint import pprint


pluginopt = {'plugin': os.path.join(os.path.dirname(__file__), "paytest.py")}
EXPERIMENTAL_FEATURES = int(os.environ.get("EXPERIMENTAL_FEATURES", "0"))


def test_start(node_factory):
    node_factory.get_node(options=pluginopt)


def test_invoice(node_factory):
    l1 = node_factory.get_node(options=pluginopt)
    inv = l1.rpc.testinvoice('03' * 33)
    details = l1.rpc.decodepay(inv['invoice'])
    pprint(details)


def test_simple_pay(node_factory):
    """ l1 generates and pays an invoice on behalf of l2.
    """
    l1, l2 = node_factory.line_graph(2, opts=pluginopt, wait_for_announce=True)

    inv = l1.rpc.testinvoice(destination=l2.info['id'], amount=1)['invoice']
    details = l1.rpc.decodepay(inv)
    pprint(details)

    # Paying the invoice without the reinterpretation from paytest
    # will cause an unknown payment details directly.
    with pytest.raises(RpcError, match=r'WIRE_INCORRECT_OR_UNKNOWN_PAYMENT_DETAILS'):
        l1.rpc.pay(inv)


def test_mpp_pay(node_factory):
    """ l1 send a payment that is going to be split.
    """
    l1, l2 = node_factory.line_graph(2, opts=pluginopt, wait_for_announce=True)
    res = l1.rpc.paytest(l2.info['id'], 2 * 10**8)

    l2.daemon.wait_for_log(r'Received 200000000/200000000 with [0-9]+ parts')

    parts = res['status']['attempts']
    assert len(parts) > 2  # Initial split + >1 part

    failures = [p['failure']['data'] for p in parts if 'failure' in p and 'data' in p['failure']]
    pprint(failures)

    outcomes = [f['failcode'] for f in failures]
    is16399 = [p == 16399 for p in outcomes]
    assert all(is16399)
    assert len(is16399) >= 1


def test_incoming_payment(node_factory):
    """Ensure that we don't fail if the payment is not a paytest.
    """
    l1, l2 = node_factory.line_graph(2, opts=pluginopt, wait_for_announce=True)
    inv = l2.rpc.invoice(42, 'lbl', 'desc')['bolt11']
    l1.rpc.pay(inv)

    plugins = [p['name'] for p in l2.rpc.listconfigs()['plugins']]
    assert 'paytest.py' in plugins

    plugins = [p['name'] for p in l1.rpc.listconfigs()['plugins']]
    assert 'paytest.py' in plugins
