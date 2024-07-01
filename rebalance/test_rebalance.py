import os
from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.client import Millisatoshi

plugin_path = os.path.join(os.path.dirname(__file__), "rebalance.py")
plugin_opt = {"plugin": plugin_path}


# waits for a bunch of nodes HTLCs to settle
def wait_for_all_htlcs(nodes):
    for n in nodes:
        n.wait_for_htlcs()


# waits for all nodes to have all scids gossip active
def wait_for_all_active(nodes, scids):
    for n in nodes:
        for scid in scids:
            n.wait_channel_active(scid)


def test_rebalance_starts(node_factory):
    l1 = node_factory.get_node()
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.daemon.wait_for_log("Plugin rebalance initialized.*")
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.daemon.wait_for_log("Plugin rebalance initialized.*")
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()
    # Start at 0 and 're-await' the two inits above. Otherwise this is flaky.
    l1.daemon.logsearch_start = 0
    l1.daemon.wait_for_logs(
        [
            "Plugin rebalance initialized.*",
            "Plugin rebalance initialized.*",
            "Plugin rebalance initialized.*",
        ]
    )


def test_rebalance_manual(node_factory, bitcoind):
    l1, l2, l3 = node_factory.line_graph(3, opts=plugin_opt)
    l1.daemon.logsearch_start = 0
    l1.daemon.wait_for_log("Plugin rebalance initialized.*")
    nodes = [l1, l2, l3]

    # form a circle so we can do rebalancing
    l3.connect(l1)
    l3.fundchannel(l1)

    # get scids
    scid12 = l1.get_channel_scid(l2)
    scid23 = l2.get_channel_scid(l3)
    scid31 = l3.get_channel_scid(l1)
    scids = [scid12, scid23, scid31]

    # wait for each others gossip
    bitcoind.generate_block(6)
    for n in nodes:
        for scid in scids:
            n.wait_channel_active(scid)

    # check we can do an auto amount rebalance
    result = l1.rpc.rebalance(scid12, scid31)
    print(result)
    assert result["status"] == "complete"
    assert result["outgoing_scid"] == scid12
    assert result["incoming_scid"] == scid31
    assert result["hops"] == 3
    assert result["received"] == "500000000msat"

    # wait until listpeers is up2date
    wait_for_all_htlcs(nodes)

    # check that channels are now balanced
    c12 = l1.rpc.listpeerchannels(l2.info["id"])["channels"][0]
    c13 = l1.rpc.listpeerchannels(l3.info["id"])["channels"][0]
    assert (
        abs(0.5 - (Millisatoshi(c12["to_us_msat"]) / Millisatoshi(c12["total_msat"])))
        < 0.01
    )
    assert (
        abs(0.5 - (Millisatoshi(c13["to_us_msat"]) / Millisatoshi(c13["total_msat"])))
        < 0.01
    )

    # check we can do a manual amount rebalance in the other direction
    result = l1.rpc.rebalance(scid31, scid12, "250000000msat")
    assert result["status"] == "complete"
    assert result["outgoing_scid"] == scid31
    assert result["incoming_scid"] == scid12
    assert result["hops"] == 3
    assert result["received"] == "250000000msat"

    # briefly check rebalancereport works
    report = l1.rpc.rebalancereport()
    assert report.get("rebalanceall_is_running") is False
    assert report.get("total_successful_rebalances") == 2


def test_rebalance_all(node_factory, bitcoind):
    l1, l2, l3 = node_factory.line_graph(3, opts=plugin_opt)
    l1.daemon.logsearch_start = 0
    l1.daemon.wait_for_log("Plugin rebalance initialized.*")
    nodes = [l1, l2, l3]

    # check we get an error if theres just one channel
    result = l1.rpc.rebalanceall()
    assert result["message"] == "Error: Not enough open channels to rebalance anything"

    # now we add another 100% outgoing liquidity to l1 which does not help
    l4 = node_factory.get_node()
    l1.connect(l4)
    l1.fundchannel(l4)

    # test this is still not possible
    result = l1.rpc.rebalanceall()
    assert result["message"] == "Error: Not enough liquidity to rebalance anything"

    # remove l4 it does not distort further testing
    l1.rpc.close(l1.get_channel_scid(l4))

    # now we form a circle so we can do actually rebalanceall
    l3.connect(l1)
    l3.fundchannel(l1)

    # get scids
    scid12 = l1.get_channel_scid(l2)
    scid23 = l2.get_channel_scid(l3)
    scid31 = l3.get_channel_scid(l1)
    scids = [scid12, scid23, scid31]

    # wait for each others gossip
    bitcoind.generate_block(6)
    wait_for_all_active(nodes, scids)

    # check that theres nothing to stop when theres nothing to stop
    result = l1.rpc.rebalancestop()
    assert result["message"] == "No rebalance is running, nothing to stop."

    # check the rebalanceall starts
    result = l1.rpc.rebalanceall(feeratio=5.0)  # we need high fees to work
    assert result["message"].startswith("Rebalance started")
    l1.daemon.wait_for_logs(
        [f"tries to rebalance: {scid12} -> {scid31}", "Automatic rebalance finished"]
    )

    # check additional calls to stop return 'nothing to stop' + last message
    result = l1.rpc.rebalancestop()["message"]
    assert result.startswith(
        "No rebalance is running, nothing to stop. "
        "Last 'rebalanceall' gave: Automatic rebalance finished"
    )

    # wait until listpeers is up2date
    wait_for_all_htlcs(nodes)

    # check that channels are now balanced
    c12 = l1.rpc.listpeerchannels(l2.info["id"])["channels"][0]
    c13 = l1.rpc.listpeerchannels(l3.info["id"])["channels"][0]
    assert (
        abs(0.5 - (Millisatoshi(c12["to_us_msat"]) / Millisatoshi(c12["total_msat"])))
        < 0.01
    )
    assert (
        abs(0.5 - (Millisatoshi(c13["to_us_msat"]) / Millisatoshi(c13["total_msat"])))
        < 0.01
    )

    # briefly check rebalancereport works
    report = l1.rpc.rebalancereport()
    assert report.get("rebalanceall_is_running") is False
    assert report.get("total_successful_rebalances") == 2
