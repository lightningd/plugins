import os
import random
import string

from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.testing.utils import wait_for


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
    l1.daemon.opts["feeadjuster-median-multiplier"] = 0.8
    l1.start()
    # Start at 0 and 're-await' the two inits above. Otherwise this is flaky.
    l1.daemon.logsearch_start = 0
    l1.daemon.wait_for_logs(
        [
            "Plugin feeadjuster initialized.*",
            "Plugin feeadjuster initialized.*",
            "Plugin feeadjuster initialized.*",
        ]
    )
    l1.rpc.plugin_stop(plugin_path)

    # We adjust fees in init
    l1, l2, l3 = node_factory.line_graph(3, wait_for_announce=True)
    scid_A = l2.rpc.listpeerchannels(l1.info["id"])["channels"][0]["short_channel_id"]
    scid_B = l2.rpc.listpeerchannels(l3.info["id"])["channels"][0]["short_channel_id"]
    l2.rpc.plugin_start(plugin_path)
    l2.daemon.wait_for_logs(
        [f"Adjusted fees of {scid_A}.*", f"Adjusted fees of {scid_B}.*"]
    )


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
    label = "".join(random.choices(string.ascii_letters, k=20))
    invoice = ll.rpc.invoice(amount, label, "desc")
    route = l.rpc.getroute(ll.info["id"], amount, riskfactor=0, fuzzpercent=0)
    l.rpc.sendpay(
        route["route"],
        invoice["payment_hash"],
        payment_secret=invoice.get("payment_secret"),
    )
    l.rpc.waitsendpay(invoice["payment_hash"])
    l.wait_for_htlcs()


def sync_gossip(nodes, scids):
    node = nodes[0]
    nodes = nodes[1:]
    for scid in scids:
        for n in nodes:
            wait_for(lambda: node.rpc.listchannels(scid) == n.rpc.listchannels(scid))


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
        "may_reconnect": True,
    }
    l1, l2, l3 = node_factory.line_graph(
        3,
        opts=[{"may_reconnect": True}, l2_opts, {"may_reconnect": True}],
        wait_for_announce=True,
    )

    chan_A = l2.rpc.listpeerchannels(l1.info["id"])["channels"][0]
    chan_B = l2.rpc.listpeerchannels(l3.info["id"])["channels"][0]
    scid_A = chan_A["short_channel_id"]
    scid_B = chan_B["short_channel_id"]
    nodes = [l1, l2, l3]
    scids = [scid_A, scid_B]

    # Fees don't get updated until there is a forwarding event!
    assert all([get_chan_fees(l2, scid) == (base_fee, ppm_fee) for scid in scids])

    chan_total = int(chan_A["total_msat"])
    assert chan_total == int(chan_B["total_msat"])

    # The first payment will trigger fee adjustment, no matter its value
    amount = int(chan_total * 0.04)
    pay(l1, l3, amount)
    wait_for(
        lambda: all([get_chan_fees(l2, scid) != (base_fee, ppm_fee) for scid in scids])
    )
    wait_for(lambda: l2.daemon.is_in_log("maybe_adjust_fees done"))

    # Send most of the balance to the other side..
    amount = int(chan_total * 0.8)
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs(
        [
            f"Adjusted fees of {scid_A} with a ratio of 0.2",
            f"Adjusted fees of {scid_B} with a ratio of 3.",
        ]
    )

    # ..And back, but first reconnect so old cln nodes gossip properly
    l2.rpc.disconnect(l1.info["id"], True)
    l2.rpc.disconnect(l3.info["id"], True)
    l2.rpc.connect(l1.info["id"], "localhost", l1.port)
    l2.rpc.connect(l3.info["id"], "localhost", l3.port)
    sync_gossip(nodes, scids)
    pay(l3, l1, amount)
    l2.daemon.wait_for_logs(
        [
            f"Adjusted fees of {scid_A} with a ratio of 6.",
            f"Adjusted fees of {scid_B} with a ratio of 0.1",
        ]
    )

    # Sending a payment worth 3% of the channel balance should not trigger
    # fee adjustment
    l2.rpc.disconnect(l1.info["id"], True)
    l2.rpc.disconnect(l3.info["id"], True)
    l2.rpc.connect(l1.info["id"], "localhost", l1.port)
    l2.rpc.connect(l3.info["id"], "localhost", l3.port)
    sync_gossip(nodes, scids)
    fees_before = [get_chan_fees(l2, scid) for scid in [scid_A, scid_B]]
    amount = int(chan_total * 0.03)
    pay(l1, l3, amount)
    l2.rpc.disconnect(l1.info["id"], True)
    l2.rpc.disconnect(l3.info["id"], True)
    l2.rpc.connect(l1.info["id"], "localhost", l1.port)
    l2.rpc.connect(l3.info["id"], "localhost", l3.port)
    sync_gossip(nodes, scids)
    assert fees_before == [get_chan_fees(l2, scid) for scid in scids]

    # But sending another 3%-worth payment does trigger adjustment (total sent
    # since last adjustment is >5%)
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs(
        [
            f"Adjusted fees of {scid_A} with a ratio of 4.",
            f"Adjusted fees of {scid_B} with a ratio of 0.2",
        ]
    )


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
    l1, l2, l3 = node_factory.line_graph(
        3, opts=[{}, l2_opts, {}], wait_for_announce=True
    )

    chan_A = l2.rpc.listpeerchannels(l1.info["id"])["channels"][0]
    chan_B = l2.rpc.listpeerchannels(l3.info["id"])["channels"][0]
    scid_A = chan_A["short_channel_id"]
    scid_B = chan_B["short_channel_id"]
    scids = [scid_A, scid_B]
    default_fees = [(base_fee, ppm_fee), (base_fee, ppm_fee)]

    chan_total = int(chan_A["total_msat"])
    assert chan_total == int(chan_B["total_msat"])
    l2.daemon.logsearch_start = 0
    l2.daemon.wait_for_log("imbalance of 30%/70%")

    # we force feeadjust initially to test this method and check if it applies
    # default fees when balancing the channel below
    l2.rpc.feeadjust()
    l2.daemon.wait_for_logs([f"Adjusted fees.*{scid_A}", f"Adjusted fees.*{scid_B}"])
    log_offset = len(l2.daemon.logs)
    wait_for_not_fees(l2, scids, default_fees[0])

    # First bring channel to somewhat of a balance
    amount = int(chan_total * 0.5)
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs(
        [
            f"Set default fees as imbalance is too low for {scid_A}",
            f"Set default fees as imbalance is too low for {scid_B}",
        ]
    )
    wait_for_fees(l2, scids, default_fees[0])

    # Because of the 70/30 imbalance limiter, a 15% payment must not yet trigger
    # 50% + 15% = 65% .. which is < 70%
    amount = int(chan_total * 0.15)
    pay(l1, l3, amount)
    assert not l2.daemon.is_in_log("Adjusted fees", log_offset)

    # Sending another 20% must now trigger because the imbalance
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs([f"Adjusted fees.*{scid_A}", f"Adjusted fees.*{scid_B}"])
    wait_for_not_fees(l2, scids, default_fees[0])

    # Bringing it back must cause default fees
    pay(l3, l1, amount)
    l2.daemon.wait_for_logs(
        [
            f"Set default fees as imbalance is too low for {scid_A}",
            f"Set default fees as imbalance is too low for {scid_B}",
        ]
    )
    wait_for_fees(l2, scids, default_fees[0])


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
    l1, l2, l3 = node_factory.line_graph(
        3, fundamount=10**6, opts=[{}, l2_opts, {}], wait_for_announce=True
    )

    chan_A = l2.rpc.listpeerchannels(l1.info["id"])["channels"][0]
    chan_B = l2.rpc.listpeerchannels(l3.info["id"])["channels"][0]
    scid_A = chan_A["short_channel_id"]
    scid_B = chan_B["short_channel_id"]
    scids = [scid_A, scid_B]
    default_fees = [(base_fee, ppm_fee), (base_fee, ppm_fee)]

    chan_total = int(chan_A["total_msat"])
    assert chan_total == int(chan_B["total_msat"])
    l2.daemon.logsearch_start = 0
    l2.daemon.wait_for_log("enough_liquidity: 100000000msat")

    # we force feeadjust initially to test this method and check if it applies
    # default fees when balancing the channel below
    l2.rpc.feeadjust()
    l2.daemon.wait_for_logs([f"Adjusted fees.*{scid_A}", f"Adjusted fees.*{scid_B}"])
    wait_for_not_fees(l2, scids, default_fees[0])

    # Bring channels to beyond big enough liquidity with 0.003btc
    amount = 300000000
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs(
        [
            f"Adjusted fees of {scid_A} with a ratio of 1.0",
            f"Adjusted fees of {scid_B} with a ratio of 1.0",
        ]
    )
    log_offset = len(l2.daemon.logs)
    wait_for_fees(l2, scids, default_fees[0])

    # Let's move another 0.003btc -> the channels will be at 0.006btc
    amount = 300000000
    pay(l1, l3, amount)
    wait_for(lambda: l2.daemon.is_in_log("maybe_adjust_fees done", log_offset))
    assert not l2.daemon.is_in_log("Adjusted fees", log_offset)

    # Sending another 0.0033btc will result in a channel balance of 0.0093btc
    # It must trigger because the remaining liquidity is not big enough
    amount = 330000000
    pay(l1, l3, amount)
    l2.daemon.wait_for_logs([f"Adjusted fees.*{scid_A}", f"Adjusted fees.*{scid_B}"])
    wait_for_not_fees(l2, scids, default_fees[0])


def test_feeadjuster_median(node_factory):
    """
    A rather simple network:

            a                b              c
    l1  <=======>   l2   <=======>  l3  <=======> l4

    l2 will adjust its configuration-set base and proportional fees for
    channels A and B as l1 and l3 exchange payments.
    l4 is needed so l2 can make a median peers-of-peer calculation on l3.
    """
    opts = {
        "fee-base": 1337,
        "fee-per-satoshi": 42,
    }
    l2_opts = {
        "fee-base": 1000,
        "fee-per-satoshi": 100,
        "plugin": plugin_path,
        "feeadjuster-deactivate-fuzz": None,
        "feeadjuster-imbalance": 0.5,
        "feeadjuster-feestrategy": "median",
        "feeadjuster-basefee": True,
    }
    l1, l2, l3, _ = node_factory.line_graph(
        4, opts=[opts, l2_opts, opts, opts], wait_for_announce=True
    )

    scid_a = l2.rpc.listpeerchannels(l1.info["id"])["channels"][0]["short_channel_id"]
    scid_b = l2.rpc.listpeerchannels(l3.info["id"])["channels"][0]["short_channel_id"]

    # we do a manual feeadjust
    l2.rpc.feeadjust()
    l2.daemon.wait_for_logs([f"Adjusted fees.*{scid_a}", f"Adjusted fees.*{scid_b}"])

    # since there is only l4 with channel c towards l3, l2 should take that value
    chan_b = l2.rpc.listpeerchannels(l3.info["id"])["channels"][0]
    assert chan_b["fee_base_msat"] == 1337
    assert (
        chan_b["fee_proportional_millionths"] < 42
    )  # we could do the actual ratio math, but meh


def test_excludelist(node_factory, directory):
    opts1 = {"may_reconnect": True}
    opts2 = {
        "may_reconnect": True,
        "plugin": plugin_path,
        "feeadjuster-deactivate-fee-update": None,
        "feeadjuster-deactivate-fuzz": None,
        "feeadjuster-imbalance": 0.5,
    }
    l1, l2, l3 = node_factory.line_graph(
        3, opts=[opts1, opts2, opts1], wait_for_announce=True
    )

    scid_a = l2.rpc.listpeerchannels(l1.info["id"])["channels"][0]["short_channel_id"]
    scid_b = l2.rpc.listpeerchannels(l3.info["id"])["channels"][0]["short_channel_id"]

    # without exclude list a notification is printed
    assert l2.rpc.feeadjust(scid_a) == "1 channel(s) adjusted"
    assert l2.daemon.is_in_log(
        "There is no feeadjuster-exclude.list given, applying the options to the channels with all peers."
    )

    # stop l2, create a exlude list file containing [l1_id] and restart l2
    l2.stop()
    l2path = os.path.join(directory, "lightning-2", "regtest")
    file = open(os.path.join(l2path, "feeadjuster-exclude.list"), "w+")
    file.write(l1.info["id"])
    file.close()
    l2.start()
    l2.daemon.is_in_log(f"Excluding the channels with the nodes: ['{l1.info['id']}']")
    l2.connect(l1)
    l2.connect(l3)

    # Do some payments to have a proper imbalance and check
    pay(l1, l2, 10**8)
    assert l2.rpc.feeadjust(scid_a) == "0 channel(s) adjusted"
    pay(l2, l3, 10**8)
    assert l2.rpc.feeadjust(scid_b) == "1 channel(s) adjusted"
