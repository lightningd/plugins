from pyln.testing.fixtures import *
from pyln.testing.utils import DEVELOPER
from pyln.client import RpcError, Millisatoshi
from utils import *
import unittest


pluginopt = {'plugin': os.path.join(os.path.dirname(__file__), "drain.py")}


@unittest.skipIf(not DEVELOPER, "slow gossip, needs DEVELOPER=1")
def test_drain_and_refill(node_factory, bitcoind):
    # SETUP: A basic circular setup to run drain and fill tests
    #
    #   l1---l2
    #    |    |
    #   l4---l3
    #

    l1, l2, l3, l4 = node_factory.line_graph(4, opts=pluginopt)
    l4.rpc.connect(l1.info['id'], 'localhost', l1.port)

    scid12 = l1.get_channel_scid(l2)
    scid23 = l2.get_channel_scid(l3)
    scid34 = l3.get_channel_scid(l4)
    scid41 = l4.fund_channel(l1, 10**6)

    # wait for each others gossip
    bitcoind.generate_block(6)
    for n in [l1,l2,l3,l4]:
        for scid in [scid12,scid23,scid34,scid41]:
            n.wait_channel_active(scid)


    # do some draining and filling
    ours_before = get_ours(l1, scid12)
    assert(l1.rpc.drain(scid12))
    ours_after = wait_ours(l1, scid12, ours_before)
    assert(ours_after < ours_before * 0.05)  # account some reserves

    # refill again with 100% should not be possible in a line_graph circle,
    # as we also paid some fees earlier and lost a tiny bit of total capacity.
    with pytest.raises(RpcError, match=r"Outgoing capacity problem"):
        l1.rpc.fill(scid12)

    # refill to 99.9% should work however
    assert(l1.rpc.fill(scid12, 99.9))


@unittest.skipIf(not DEVELOPER, "slow gossip, needs DEVELOPER=1")
def test_setbalance(node_factory, bitcoind):
    # SETUP: a basic circular setup to run setbalance tests
    #
    #   l1---l2
    #    |    |
    #   l4---l3
    #

    l1, l2, l3, l4 = node_factory.line_graph(4, opts=pluginopt)
    l4.rpc.connect(l1.info['id'], 'localhost', l1.port)

    scid12 = l1.get_channel_scid(l2)
    scid23 = l2.get_channel_scid(l3)
    scid34 = l3.get_channel_scid(l4)
    scid41 = l4.fund_channel(l1, 10**6)

    # wait for each others gossip
    bitcoind.generate_block(6)
    for n in [l1,l2,l3,l4]:
        for scid in [scid12,scid23,scid34,scid41]:
            n.wait_channel_active(scid)

    # test auto 50/50 balancing
    ours_before = get_ours(l1, scid12)
    assert(l1.rpc.setbalance(scid12))
    ours_after = wait_ours(l1, scid12, ours_before)
    # TODO: can we fix/change/improve this to be more precise?
    assert(ours_after < ours_before * 0.52)
    assert(ours_after > ours_before * 0.48)

    # set and test some 70/30 specific balancing
    assert(l1.rpc.setbalance(scid12, 30))
    ours_after = wait_ours(l1, scid12, ours_after)
    assert(ours_after < ours_before * 0.33)
    assert(ours_after > ours_before * 0.27)

    assert(l1.rpc.setbalance(scid12, 70))
    ours_after = wait_ours(l1, scid12, ours_after)
    assert(ours_after < ours_before * 0.73)
    assert(ours_after > ours_before * 0.67)


# helper function that balances incoming capacity, so autodetection edge case
# testing gets a lot simpler.
def balance(node, node_a, scid_a, node_b, scid_b, node_c):
    msat_a = get_ours(node_a, scid_a)
    msat_b = get_ours(node_b, scid_b)
    if (msat_a > msat_b):
        node.pay(node_b, msat_a - msat_b)
        node_b.pay(node_c, msat_a - msat_b)
    if (msat_b > msat_a):
        node.pay(node_a, msat_b - msat_a)
        node_a.pay(node_c, msat_b - msat_a)
    wait_for_all_htlcs([node, node_a, node_b])


def test_drain_chunks(node_factory, bitcoind):
    # SETUP: a small mesh that enables testing chunks
    #
    #   l2--    --l3
    #   |   \  /   |
    #   |    l1    |
    #   |    ||    |
    #   |    ||    |
    #   o----l4----o
    #
    # In such a scenario we can disstribute the funds in such a way
    # that only correct chunking allows rebalancing for l1
    #
    # FUNDING:
    #  scid12:  l1 -> l2   10**6
    #  scid13:  l1 -> l3   10**6
    #  scid24:  l2 -> l4   10**6
    #  scid34:  l4 -> l4   10**6
    #  scid41:  l4 -> l1   11**6   (~1.750.000 sat)

    l1, l2, l3, l4 = node_factory.get_nodes(4, opts=pluginopt)
    l1.connect(l2)
    l1.connect(l3)
    l2.connect(l4)
    l3.connect(l4)
    l4.connect(l1)
    scid12 = l1.fund_channel(l2, 10**6)
    scid13 = l1.fund_channel(l3, 10**6)
    scid24 = l2.fund_channel(l4, 10**6)
    scid34 = l3.fund_channel(l4, 10**6)
    scid41 = l4.fund_channel(l1, 11**6)
    nodes = [l1, l2, l3, l4]
    scids = [scid12, scid13, scid24, scid34, scid41]

    # wait for each others gossip
    bitcoind.generate_block(6)
    for n in nodes:
        for scid in scids:
            n.wait_channel_active(scid)
    amount = get_ours(l4, scid41)

    # drain in one chunk should be impossible and detected before doing anything
    with pytest.raises(RpcError, match=r"Selected chunks \(1\) will not fit incoming channel capacities."):
        l4.rpc.drain(scid41, 100, 1)

    # using 3 chunks should also not be possible, as it would overfill one of the incoming channels
    with pytest.raises(RpcError, match=r"Selected chunks \(3\) will not fit incoming channel capacities."):
        l4.rpc.drain(scid41, 100, 3)

    # test chunk autodetection and even chunks 2,4,6
    assert(l4.rpc.drain(scid41))
    wait_for_all_htlcs(nodes)
    assert(get_ours(l1, scid41) > amount * 0.9)
    balance(l1, l2, scid12, l3, scid13, l4)
    assert(l1.rpc.drain(scid41))
    wait_for_all_htlcs(nodes)
    assert(get_theirs(l1, scid41) > amount * 0.9)
    assert(l4.rpc.drain(scid41, 100, 2))
    wait_for_all_htlcs(nodes)
    assert(get_ours(l1, scid41) > amount * 0.9)
    assert(l1.rpc.drain(scid41, 100, 2))
    wait_for_all_htlcs(nodes)
    assert(get_theirs(l1, scid41) > amount * 0.9)
    assert(l4.rpc.drain(scid41, 100, 4))
    wait_for_all_htlcs(nodes)
    assert(get_ours(l1, scid41) > amount * 0.9)
    assert(l1.rpc.drain(scid41, 100, 4))
    wait_for_all_htlcs(nodes)
    assert(get_theirs(l1, scid41) > amount * 0.9)
    assert(l4.rpc.drain(scid41, 100, 6))
    wait_for_all_htlcs(nodes)
    assert(get_ours(l1, scid41) > amount * 0.9)
    assert(l1.rpc.drain(scid41, 100, 6))
    wait_for_all_htlcs(nodes)
    assert(get_theirs(l1, scid41) > amount * 0.9)


@unittest.skipIf(not DEVELOPER, "slow gossip, needs DEVELOPER=1")
def test_fill_chunks(node_factory, bitcoind):
    # SETUP: a small mesh that enables testing chunks
    #
    #   l2--    --l3
    #   |   \  /   |
    #   |    l1    |
    #   |    ||    |
    #   |    ||    |
    #   o----l4----o
    #
    # In such a scenario we can disstribute the funds in such a way
    # that only correct chunking allows rebalancing for l1
    #
    # FUNDING:
    #  scid12:  l1 -> l2   10**6
    #  scid13:  l1 -> l3   10**6
    #  scid24:  l2 -> l4   10**6
    #  scid34:  l4 -> l4   10**6
    #  scid41:  l4 -> l1   11**6   (~1.750.000 sat)

    l1, l2, l3, l4 = node_factory.get_nodes(4, opts=pluginopt)
    l1.connect(l2)
    l1.connect(l3)
    l2.connect(l4)
    l3.connect(l4)
    l4.connect(l1)
    scid12 = l1.fund_channel(l2, 10**6)
    scid13 = l1.fund_channel(l3, 10**6)
    scid24 = l2.fund_channel(l4, 10**6)
    scid34 = l3.fund_channel(l4, 10**6)
    scid41 = l4.fund_channel(l1, 11**6)
    nodes = [l1, l2, l3, l4]
    scids = [scid12, scid13, scid24, scid34, scid41]

    # wait for each others gossip
    bitcoind.generate_block(6)
    for n in nodes:
        for scid in scids:
            n.wait_channel_active(scid)
    amount = get_ours(l4, scid41)

    # fill in one chunk should be impossible and detected before doing anything
    with pytest.raises(RpcError, match=r"Selected chunks \(1\) will not fit outgoing channel capacities."):
        l1.rpc.fill(scid41, 100, 1)

    # using 3 chunks should also not be possible, as it would overdrain one of the outgoing channels
    with pytest.raises(RpcError, match=r"Selected chunks \(3\) will not fit outgoing channel capacities."):
        print(l1.rpc.fill(scid41, 100, 3))

    # test chunk autodetection and even chunks 2,4,6
    assert(l1.rpc.fill(scid41))
    wait_for_all_htlcs(nodes)
    assert(get_ours(l1, scid41) > amount * 0.9)
    balance(l1, l2, scid12, l3, scid13, l4)
    assert(l4.rpc.fill(scid41))
    wait_for_all_htlcs(nodes)
    assert(get_theirs(l1, scid41) > amount * 0.9)
    assert(l1.rpc.fill(scid41, 100, 2))
    wait_for_all_htlcs(nodes)
    assert(get_ours(l1, scid41) > amount * 0.9)
    assert(l4.rpc.fill(scid41, 100, 2))
    wait_for_all_htlcs(nodes)
    assert(get_theirs(l1, scid41) > amount * 0.9)
    assert(l1.rpc.fill(scid41, 100, 4))
    wait_for_all_htlcs(nodes)
    assert(get_ours(l1, scid41) > amount * 0.9)
    assert(l4.rpc.fill(scid41, 100, 4))
    wait_for_all_htlcs(nodes)
    assert(get_theirs(l1, scid41) > amount * 0.9)
