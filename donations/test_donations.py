import os
import re
import time
import pytest
from pyln.testing.fixtures import *  # noqa: F401,F403
import requests

plugin_path = os.path.join(os.path.dirname(__file__), "donations.py")


def test_donation_starts(node_factory):
    l1 = node_factory.get_node()
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
    l1 = node_factory.get_node(options=pluginopt)
    port = node_factory.get_unused_port()
    l1.rpc.donationserver("start", port)
    l1.daemon.wait_for_log(
        f"plugin-donations.py:.*Starting donation server on port {port} on all addresses"
    )

    session = requests.Session()

    response = session.get(f"http://127.0.0.1:{port}/donation")
    assert response.status_code == 200
    assert "Leave a donation" in response.text

    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text)
    assert match, "Could not find CSRF token"
    csrf_token = match.group(1)

    response = session.post(
        f"http://127.0.0.1:{port}/donation",
        data={
            "csrf_token": csrf_token,
            "amount": "1000",
            "description": "Test donation from pytest",
        },
    )
    assert response.status_code == 200
    assert "The CSRF token is missing" not in response.text

    assert "data:image/png" in response.text

    match = re.search(r'value="(lnbc[^"]+)"', response.text)
    assert match, "No bolt11 invoice found in response"
    bolt11 = match.group(1)
    l1.rpc.call("xpay", [bolt11])
    label = l1.rpc.call("listinvoices", {"invstring": bolt11})["invoices"][0]["label"]

    max_attempts = 10
    for attempt in range(max_attempts):
        response = session.get(f"http://127.0.0.1:{port}/is_invoice_paid/{label}")

        if response.text != "waiting":
            # Payment detected!
            assert (
                "Your donation has been received and is well appricated."
                in response.text
            )
            break

        time.sleep(1)
    else:
        pytest.fail("Payment was not detected after 10 seconds")

    response = session.get(f"http://127.0.0.1:{port}/donation")
    assert "1000 Satoshi" in response.text
    assert "Test donation from pytest" in response.text

    msg = l1.rpc.donationserver("stop", port)
    assert msg == f"stopped server on port {port}"
