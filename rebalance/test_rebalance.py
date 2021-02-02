import os
from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.client import Millisatoshi

plugin_path = os.path.join(os.path.dirname(__file__), "rebalance.py")
plugin_opt = {'plugin': plugin_path}


# waits for a bunch of nodes HTLCs to settle
def wait_for_all_htlcs(nodes):
    for n in nodes:
        n.wait_for_htlcs()


def test_rebalance_starts(node_factory):
    l1 = node_factory.get_node()
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()


def test_rebalance_manual(node_factory, bitcoind):
    l1, l2, l3 = node_factory.line_graph(3, opts=plugin_opt)
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
    assert result['status'] == 'settled'
    assert result['outgoing_scid'] == scid12
    assert result['incoming_scid'] == scid31
    assert result['hops'] == 3
    assert result['received'] == '500000000msat'

    # wait until listpeers is up2date
    wait_for_all_htlcs(nodes)

    # check that channels are now balanced
    c12 = l1.rpc.listpeers(l2.info['id'])['peers'][0]['channels'][0]
    c13 = l1.rpc.listpeers(l3.info['id'])['peers'][0]['channels'][0]
    assert abs(0.5 - (Millisatoshi(c12['to_us_msat']) / Millisatoshi(c12['total_msat']))) < 0.01
    assert abs(0.5 - (Millisatoshi(c13['to_us_msat']) / Millisatoshi(c13['total_msat']))) < 0.01

    # check we can do a manual amount rebalance in the other direction
    result = l1.rpc.rebalance(scid31, scid12, '250000000msat')
    assert result['status'] == 'settled'
    assert result['outgoing_scid'] == scid31
    assert result['incoming_scid'] == scid12
    assert result['hops'] == 3
    assert result['received'] == '250000000msat'


def test_rebalance_all(node_factory, bitcoind):
    l1, l2, l3 = node_factory.line_graph(3, opts=plugin_opt)
    nodes = [l1, l2, l3]

    # check we get an error if theres just one channel
    result = l1.rpc.rebalanceall()
    assert result['message'] == 'Error: Not enough open channels to balance anything'
