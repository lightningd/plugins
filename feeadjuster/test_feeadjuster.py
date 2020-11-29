import os
import random
import string

import unittest
from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.testing.utils import DEVELOPER, wait_for


plugin_path = os.path.join(os.path.dirname(__file__), "feeadjuster.py")


def test_feeadjuster_starts(node_factory):
    l1 = node_factory.get_node()
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.daemon.wait_for_log("Plugin feeadjuster initialized.*")
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.daemon.wait_for_log("Plugin feeadjuster initialized.*")
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()
    # Start at 0 and 're-await' the two inits above. Otherwise this is flaky.
    l1.daemon.logsearch_start = 0
    l1.daemon.wait_for_logs(["Plugin feeadjuster initialized.*",
                             "Plugin feeadjuster initialized.*",
                             "Plugin feeadjuster initialized.*"])
    l1.rpc.plugin_stop(plugin_path)

    # We adjust fees in init
    l1, l2, l3 = node_factory.line_graph(3, wait_for_announce=True)
    scid_A = l2.rpc.listpeers(
        l1.info["id"])["peers"][0]["channels"][0]["short_channel_id"]
    scid_B = l2.rpc.listpeers(
        l3.info["id"])["peers"][0]["channels"][0]["short_channel_id"]
    l2.rpc.plugin_start(plugin_path)
    l2.daemon.wait_for_logs([f"Adjusted fees of {scid_A}.*",
                             f"Adjusted fees of {scid_B}.*"])


def get_chan_fees(l, scid):
    for half in l.rpc.listchannels(scid)["channels"]:
        if l.info["id"] == half["source"]:
            return (half["base_fee_millisatoshi"], half["fee_per_millionth"])


def wait_for_fees(l, scids, fees):
    for scid in scids:
        wait_for(lambda: get_chan_fees(l, scid) == fees)


def wait_for_not_fees(l, scids, fees):
    for scid in scids:
        wait_for(lambda: not get_chan_fees(l, scid) == fees)


def pay(l, ll, amount):
    label = ''.join(random.choices(string.ascii_letters, k=20))
    invoice = ll.rpc.invoice(amount, label, "desc")
    route = l.rpc.getroute(ll.info["id"], amount, riskfactor=0, fuzzpercent=0)
    l.rpc.sendpay(route["route"], invoice["payment_hash"])
    l.rpc.waitsendpay(invoice["payment_hash"])


def sync_gossip(nodes, scids):
    node = nodes[0]
    nodes = nodes[1:]
    for scid in scids:
        for n in nodes:
            wait_for(lambda: node.rpc.listchannels(scid) == n.rpc.listchannels(scid))


@unittest.skipIf(not DEVELOPER, "Too slow without fast gossip")
def test_feeadjuster_adjusts(node_factory):
    """
    A rather simple network:

            A                   B
    l1  <========>   l2   <=========>  l3

    l2 will adjust its configuration-set base and proportional fees for
    channels A and B as l1 and l3 exchange payments.
    """
    base_fee = 5000
    ppm_fee = 300
    l2_opts = {
        "fee-base": base_fee,
        "fee-per-satoshi": ppm_fee,
        "plugin": plugin_path,
        "feeadjuster-deactivate-fuzz": None,
    }
    l1, l2, l3 = node_factory.line_graph(3, opts=[{}, l2_opts, {}],
                                         wait_for_announce=True)

    chan_A = l2.rpc.listpeers(l1.info["id"])["peers"][0]["channels"][0]
    chan_B = l2.rpc.listpeers(l3.info["id"])["peers"][0]["channels"][0]
    scid_A = chan_A["short_channel_id"]
    scid_B = chan_B["short_channel_id"]
    nodes = [l1, l2, l3]
    scids = [scid_A, scid_B]

    # Fees don't get updated until there is a forwarding event!
    assert all([get_chan_fees(l2, scid) == (base_fee, ppm_fee)
                for scid in scids])

    chan_total = int(chan_A["total_msat"])
    assert chan_total == int(chan_B["total_msat"])

    # The first payment will trigger fee adjustment, no matter its value
    amount = int(chan_total * 0.04)
    pay(l1, l3, amount)
    wait_for(lambda: all([get_chan_fees(l2, scid) != (base_fee, ppm_fee)
                          for scid in scids]))

    # Send most of the balance to the other side..
    amount = int(chan_total * 0.8)
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs([f'Adjusted fees of {scid_A} with a ratio of 0.2',
                             f'Adjusted fees of {scid_B} with a ratio of 3.'])

    # ..And back
    sync_gossip(nodes, scids)
    pay(l3, l1, amount)
    l2.daemon.wait_for_logs([f'Adjusted fees of {scid_A} with a ratio of 6.',
                             f'Adjusted fees of {scid_B} with a ratio of 0.1'])

    # Sending a payment worth 3% of the channel balance should not trigger
    # fee adjustment
    sync_gossip(nodes, scids)
    fees_before = [get_chan_fees(l2, scid) for scid in [scid_A, scid_B]]
    amount = int(chan_total * 0.03)
    pay(l1, l3, amount)
    sync_gossip(nodes, scids)
    assert fees_before == [get_chan_fees(l2, scid) for scid in scids]

    # But sending another 3%-worth payment does trigger adjustment (total sent
    # since last adjustment is >5%)
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs([f'Adjusted fees of {scid_A} with a ratio of 4.',
                             f'Adjusted fees of {scid_B} with a ratio of 0.2'])


@unittest.skipIf(not DEVELOPER, "Too slow without fast gossip")
def test_feeadjuster_imbalance(node_factory):
    """
    A rather simple network:

            A                   B
    l1  <========>   l2   <=========>  l3

    l2 will adjust its configuration-set base and proportional fees for
    channels A and B as l1 and l3 exchange payments.
    """
    base_fee = 5000
    ppm_fee = 300
    l2_opts = {
        "fee-base": base_fee,
        "fee-per-satoshi": ppm_fee,
        "plugin": plugin_path,
        "feeadjuster-deactivate-fuzz": None,
        "feeadjuster-imbalance": 0.7,  # should be normalized to 30/70
    }
    l1, l2, l3 = node_factory.line_graph(3, opts=[{}, l2_opts, {}],
                                         wait_for_announce=True)

    chan_A = l2.rpc.listpeers(l1.info["id"])["peers"][0]["channels"][0]
    chan_B = l2.rpc.listpeers(l3.info["id"])["peers"][0]["channels"][0]
    scid_A = chan_A["short_channel_id"]
    scid_B = chan_B["short_channel_id"]
    scids = [scid_A, scid_B]
    default_fees = [(base_fee, ppm_fee), (base_fee, ppm_fee)]

    chan_total = int(chan_A["total_msat"])
    assert chan_total == int(chan_B["total_msat"])
    l2.daemon.wait_for_log('imbalance of 30%/70%')

    # we force feeadjust initially to test this method and check if it applies
    # default fees when balancing the channel below
    l2.rpc.feeadjust()
    l2.daemon.wait_for_logs([
        f"Adjusted fees.*{scid_A}",
        f"Adjusted fees.*{scid_B}"
    ])
    log_offset = len(l2.daemon.logs)
    wait_for_not_fees(l2, scids, default_fees[0])

    # First bring channel to somewhat of a blanance
    amount = int(chan_total * 0.5)
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs([
        f'Set default fees as imbalance is too low: {scid_A}',
        f'Set default fees as imbalance is too low: {scid_B}'
    ])
    wait_for_fees(l2, scids, default_fees[0])

    # Because of the 70/30 imbalance limiter, a 15% payment must not yet trigger
    # 50% + 15% = 65% .. which is < 70%
    amount = int(chan_total * 0.15)
    pay(l1, l3, amount)
    assert not l2.daemon.is_in_log("Adjusted fees", log_offset)

    # Sending another 20% must now trigger because the imbalance
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs([
        f"Adjusted fees.*{scid_A}",
        f"Adjusted fees.*{scid_B}"
    ])
    wait_for_not_fees(l2, scids, default_fees[0])

    # Bringing it back must cause default fees
    pay(l3, l1, amount)
    l2.daemon.wait_for_logs([
        f'Set default fees as imbalance is too low: {scid_A}',
        f'Set default fees as imbalance is too low: {scid_B}'
    ])
    wait_for_fees(l2, scids, default_fees[0])
