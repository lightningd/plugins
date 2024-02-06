from pyln.client import RpcError
from pyln.testing.fixtures import *  # noqa: F401, F403
from pyln.testing.utils import wait_for, DEVELOPER
import os
import time
import pytest
import unittest


currdir = os.path.dirname(__file__)
plugin = os.path.join(currdir, 'jitrebalance.py')
hold_plugin = os.path.join(currdir, 'tests/hold_htlcs.py')
reject_plugin = os.path.join(currdir, 'tests/refuse_htlcs.py')


@unittest.skipIf(not DEVELOPER, "gossip is too slow if we're not in developer mode")
def test_simple_rebalance(node_factory):
    """Simple rebalance that routes along a cycle to enable the original payment

    l1 ---- l2 ---- l3 ----- l4
              |    /
              |   /
              |  /
               l5

    We are going to drain the channel (l2, l3) of most of its funds and then
    ask l1 to route through [l1, l2, l3, l4]. Under normal circumstances
    that'd fail since (l2, l3) doesn't have sufficient funds. l2 however will
    attempt to rebalance (l2,l3) using a circular route (l2, l5, l3, l2) to
    get the required funds back.

    """
    print(plugin)
    opts = [{}, {'plugin': plugin}, {}, {}, {}]
    l1, l2, l3, l4, l5 = node_factory.get_nodes(5, opts=opts)
    amt = 10**7

    # Open the channels
    channels = [(l1, l2), (l3, l2), (l3, l4), (l2, l5), (l5, l3)]
    for src, dst in channels:
        src.openchannel(dst, capacity=10**6)

    # Drain (l2, l3) so that a larger payment fails later on
    chan = l2.rpc.listpeerchannels(l3.info['id'])['channels'][0]

    # Send 9 million millisatoshis + reserve + a tiny fee allowance from l3 to
    # l2 for the actual payment
    inv = l2.rpc.invoice(
        chan['our_reserve_msat'] + 9000000 + 100,
        "imbalance", "imbalance"
    )
    time.sleep(1)
    l3.rpc.pay(inv['bolt11'])

    def no_pending_htlcs():
        return l2.rpc.listpeerchannels(l3.info['id'])['channels'][0]['htlcs'] == []

    wait_for(no_pending_htlcs)

    chan = l2.rpc.listpeerchannels(l3.info['id'])['channels'][0]
    assert(int(chan['spendable_msat']) < amt)

    # Get (l2, l5) so we can exclude it when routing from l1 to l4
    scid = l2.rpc.listpeerchannels(l5.info['id'])['channels'][0]['short_channel_id']

    # The actual invoice that l1 will attempt to pay to l4, and that will be
    # larger than the current capacity of (l2, l3) so it triggers a
    # rebalancing.
    inv = l4.rpc.invoice(amt, "test", "test")

    # Now wait for gossip to settle and l1 to learn the topology so it can
    # then route the payment. We do this now since we already did what we
    # could without this info
    wait_for(lambda: len(l1.rpc.listchannels()['channels']) == 2 * len(channels))

    route = l1.rpc.getroute(node_id=l4.info['id'], msatoshi=amt, riskfactor=1,
                            exclude=[scid + '/0', scid + '/1'])['route']

    # This will succeed with l2 doing a rebalancing just-in-time !
    l1.rpc.sendpay(route, inv['payment_hash'], payment_secret=inv.get('payment_secret'))
    assert l1.rpc.waitsendpay(inv['payment_hash'])['status'] == 'complete'
    assert l2.daemon.is_in_log('Succesfully re-filled outgoing capacity')


@unittest.skipIf(not DEVELOPER, "gossip is too slow if we're not in developer mode")
def test_rebalance_failure(node_factory):
    """Same setup as the first test :

    l1 ---- l2 ---- l3 ----- l4
              |    /
              |   /
              |  /
               l5

    We now test failures (l5 rejects HTLCs, l3 takes too long to resolve it).
    """
    # First, the "no route left" case.
    opts = [{}, {'plugin': plugin, 'jitrebalance-try-timeout': 3}, {}, {},
            {'plugin': reject_plugin}]
    l1, l2, l3, l4, l5 = node_factory.get_nodes(5, opts=opts)
    amt = 10**7

    # Open the channels
    channels = [(l1, l2), (l3, l2), (l3, l4), (l2, l5), (l5, l3)]
    for src, dst in channels:
        src.openchannel(dst, capacity=10**6)

    # Drain (l2, l3) so that a larger payment fails later on
    chan = l2.rpc.listpeerchannels(l3.info['id'])['channels'][0]

    # Send 9 million millisatoshis + reserve + a tiny fee allowance from l3 to
    # l2 for the actual payment
    inv = l2.rpc.invoice(
        chan['our_reserve_msat'] + 9000000 + 100,
        "imbalance", "imbalance"
    )
    time.sleep(1)
    l3.rpc.pay(inv['bolt11'])

    def no_pending_htlcs():
        return l2.rpc.listpeerchannels(l3.info['id'])['channels'][0]['htlcs'] == []

    wait_for(no_pending_htlcs)

    chan = l2.rpc.listpeerchannels(l3.info['id'])['channels'][0]
    assert(int(chan['spendable_msat']) < amt)

    # Get (l2, l5) so we can exclude it when routing from l1 to l4
    scid = l2.rpc.listpeerchannels(l5.info['id'])['channels'][0]['short_channel_id']

    # The actual invoice that l1 will attempt to pay to l4, and that will be
    # larger than the current capacity of (l2, l3) so it triggers a
    # rebalancing.
    inv = l4.rpc.invoice(amt, "test", "test")

    # Now wait for gossip to settle and l1 to learn the topology so it can
    # then route the payment. We do this now since we already did what we
    # could without this info
    wait_for(lambda: len(l1.rpc.listchannels()['channels']) == 2 * len(channels))

    route = l1.rpc.getroute(node_id=l4.info['id'], msatoshi=amt, riskfactor=1,
                            exclude=[scid + '/0', scid + '/1'])['route']

    # This will exclude [l5, l3] and fail as there is no route left
    l1.rpc.sendpay(route, inv['payment_hash'], payment_secret=inv.get('payment_secret'))
    with pytest.raises(RpcError, match='WIRE_TEMPORARY_CHANNEL_FAILURE'):
        l1.rpc.waitsendpay(inv['payment_hash'])
    assert l2.daemon.is_in_log('Could not get a route, no remaining one?')
    l5.rpc.plugin_stop(reject_plugin)

    # Now test the timeout on number of attempts
    l3.rpc.plugin_start(hold_plugin)
    l1.rpc.sendpay(route, inv['payment_hash'], payment_secret=inv.get('payment_secret'))
    # l3 will hold on the HTLC, and at the time it rejects it, l2 won't try
    # other routes as it exceeded its timeout
    with pytest.raises(RpcError, match='WIRE_TEMPORARY_CHANNEL_FAILURE'):
        l1.rpc.waitsendpay(inv['payment_hash'])
    assert l2.daemon.is_in_log('Timed out while trying to rebalance')


@unittest.skipIf(not DEVELOPER, "gossip is too slow if we're not in developer mode")
def test_issue_88(node_factory):
    """Reproduce issue #88: crash due to unconfirmed channel.

    l2 has a channel open with l4, that is not confirmed yet, doesn't have a
    stable short_channel_id, and will crash.

    """
    l1, l2, l3 = node_factory.line_graph(3, opts=[{}, {'plugin': plugin}, {}], wait_for_announce=True)
    l4 = node_factory.get_node()

    l2.connect(l4)
    l2.rpc.fundchannel(l4.info['id'], 10**5)

    peers = l2.rpc.listpeers()['peers']
    channels = l2.rpc.listpeerchannels()['channels']

    # We should have 3 peers...
    assert(len(peers) == 3)
    # ... but only 2 channels with a short_channel_id...
    assert(sum([1 for c in channels if 'short_channel_id' in c]) == 2)
    # ... and one with l4, without a short_channel_id
    assert('short_channel_id' not in l4.rpc.listpeerchannels(l2.info['id'])['channels'][0])

    # Now if we send a payment l1 -> l2 -> l3, then l2 will stumble while
    # attempting to access the short_channel_id on the l2 -> l4 channel:
    inv = l3.rpc.invoice(1000, 'lbl', 'desc')['bolt11']
    l1.rpc.pay(inv)
