import os
import random
import string
import unittest
import time

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
    chan_total = int(chan_A["total_msat"])
    assert chan_total == int(chan_B["total_msat"])

    # Expect initial updates
    l2.daemon.logsearch_start = 0
    l2.daemon.wait_for_logs([
        f"Adjusted fees of {scid_A}",
        f"Adjusted fees of {scid_B}"
    ])

    # A small amount should not lead to an update
    amount = int(chan_total * 0.04)
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs([
        f"Skipping insignificant fee update on {scid_A}",
        f"Skipping insignificant fee update on {scid_B}",
    ])

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

    # await expected initial updates
    l2.daemon.wait_for_logs([
        f"Adjusted fees of {scid_A}",
        f"Adjusted fees of {scid_B}"
    ])
    log_offset = len(l2.daemon.logs)
    # FIXME: The next line fails, not because of this test or plugin
    # but because in clnd the channel never gets updated when setting
    # fees some milliseconds after state gets NORMAL
    wait_for_not_fees(l2, scids, default_fees[0])

    # First bring channel to somewhat of a balance
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
        f"Adjusted fees of {scid_A}",
        f"Adjusted fees of {scid_B}"
    ])
    wait_for_not_fees(l2, scids, default_fees[0])

    # Bringing it back must cause default fees
    pay(l3, l1, amount)
    l2.daemon.wait_for_logs([
        f'Set default fees as imbalance is too low: {scid_A}',
        f'Set default fees as imbalance is too low: {scid_B}'
    ])
    wait_for_fees(l2, scids, default_fees[0])


@unittest.skipIf(not DEVELOPER, "Too slow without fast gossip")
def test_feeadjuster_big_enough_liquidity(node_factory):
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
        "feeadjuster-imbalance": 0.5,
        "feeadjuster-enough-liquidity": "0.001btc",
        "feeadjuster-threshold-abs": "0.0001btc",
    }
    # channels' size: 0.01btc
    # between 0.001btc and 0.009btc the liquidity is big enough
    l1, l2, l3 = node_factory.line_graph(3, fundamount=10**6, opts=[{}, l2_opts, {}],
                                         wait_for_announce=True)

    chan_A = l2.rpc.listpeers(l1.info["id"])["peers"][0]["channels"][0]
    chan_B = l2.rpc.listpeers(l3.info["id"])["peers"][0]["channels"][0]
    scid_A = chan_A["short_channel_id"]
    scid_B = chan_B["short_channel_id"]
    scids = [scid_A, scid_B]
    default_fees = [(base_fee, ppm_fee), (base_fee, ppm_fee)]

    chan_total = int(chan_A["total_msat"])
    assert chan_total == int(chan_B["total_msat"])
    l2.daemon.logsearch_start = 0
    l2.daemon.wait_for_log('enough_liquidity: 100000000msat')

    # await expected initial updates
    l2.daemon.wait_for_logs([
        f"Adjusted fees of {scid_A}",
        f"Adjusted fees of {scid_B}"
    ])
    # FIXME: The next line fails, not because of this test or plugin
    # but because in clnd the channel never gets updated when setting
    # fees some milliseconds after state gets NORMAL
    wait_for_not_fees(l2, scids, default_fees[0])

    # Bring channels to beyond big enough liquidity with 0.003btc
    amount = 300000000
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs([
        f"Adjusted fees of {scid_A} with a ratio of 1.0",
        f"Adjusted fees of {scid_B} with a ratio of 1.0"
    ])
    log_offset = len(l2.daemon.logs)
    wait_for_fees(l2, scids, default_fees[0])

    # Let's move another 0.003btc -> the channels will be at 0.006btc
    amount = 300000000
    pay(l1, l3, amount)
    l2.wait_for_htlcs()
    assert not l2.daemon.is_in_log("Adjusted fees", log_offset)

    # Sending another 0.0033btc will result in a channel balance of 0.0093btc
    # It must trigger because the remaining liquidity is not big enough
    amount = 330000000
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs([
        f"Adjusted fees of {scid_A}",
        f"Adjusted fees of {scid_B}"
    ])
    wait_for_not_fees(l2, scids, default_fees[0])


@unittest.skipIf(not DEVELOPER, "Too slow without fast gossip")
def test_initial_updates(node_factory):
    """
            A                   B
    l1  <========>   l2   <=========>  l3

    - Bring the channel to some mixed balance.
    - Check it did its regular feeadjust updates
    - Restart l2 and check if those updates are skipped in the initial loop
      as they should be insignificant because balance didn't change.

    This will currently fail for two reasons:
     1. The initial fee update on the newly created, 100% distorted, channels
       is missing. The first time the plugin comes up, it adjusts 0 channels,
       even though the channels need to be adjusted.
     2. After usage and expected adjustments, stop and restart should not
        do the same channel fee update again, but it does (unnecessarily).
    """
    # setup and fetch infos
    opts = {'may_reconnect': True}
    l2_opts = {'may_reconnect': True,
               "plugin": plugin_path,
               "feeadjuster-deactivate-fuzz": None}
    l1, l2, l3 = node_factory.line_graph(3, opts=[opts, l2_opts, opts],
                                         wait_for_announce=True)
    chan_A = l2.rpc.listpeers(l1.info["id"])["peers"][0]["channels"][0]
    chan_B = l2.rpc.listpeers(l3.info["id"])["peers"][0]["channels"][0]
    scid_A = chan_A["short_channel_id"]
    scid_B = chan_B["short_channel_id"]
    chan_total = chan_A["total_msat"]

    # wait for expected initial updates after channel creation
    # because these channels are totally distorted
    l2.daemon.logsearch_start = 0
    l2.daemon.wait_for_logs([
        f"Adjusted fees of {scid_A}",
        f"Adjusted fees of {scid_B}"
    ])

    # bring channels to some not totally distorted balance
    pay(l1, l3, chan_total * 0.25)
    l2.daemon.wait_for_logs([
        f"Adjusted fees of {scid_A}",
        f"Adjusted fees of {scid_B}"
    ])

    # We test skipping of insignificants updates on the fly here
    pay(l1, l3, chan_total * 0.01)
    l2.daemon.wait_for_logs([
        f"Skipping insignificant fee update on {scid_A}",
        f"Skipping insignificant fee update on {scid_B}",
    ])

    # Now stop and restart and dont expect any further updates
    logsearch = l2.daemon.logsearch_start
    l2.restart()
    l2.connect(l1)
    l2.connect(l3)
    l2.daemon.wait_for_log("Plugin feeadjuster initialized.*")
    l2.daemon.wait_for_log("0 channels adjusted")
    # wait for potential channel_state_changed to NORMAL caused updates
    wait_for(lambda: l2.rpc.listpeers(l1.info["id"])['peers'][0]['connected'])
    wait_for(lambda: l2.rpc.listpeers(l3.info["id"])['peers'][0]['connected'])
    time.sleep(1)
    assert not l2.daemon.is_in_log(f".*Adjusted fees of {scid_A}.*", logsearch)
    assert not l2.daemon.is_in_log(f".*Adjusted fees of {scid_B}.*", logsearch)
