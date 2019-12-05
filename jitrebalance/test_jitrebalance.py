from pyln.testing.fixtures import *  # noqa: F401, F403
from pyln.testing.utils import wait_for
from pprint import pprint
import os
import time
import unittest


plugin = os.path.join(os.path.dirname(__file__), 'jitrebalance.py')


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
    chan = l2.rpc.listpeers(l3.info['id'])['peers'][0]['channels'][0]
    pprint(chan)
    # Send 9 million millisatoshis + reserve + a tiny fee allowance from l3 to
    # l2 for the actual payment
    inv = l2.rpc.invoice(
        chan['our_channel_reserve_satoshis']*1000 + 9000000 + 100,
        "imbalance", "imbalance"
    )
    time.sleep(1)
    l3.rpc.pay(inv['bolt11'])

    def no_pending_htlcs():
        peer = l2.rpc.listpeers(l3.info['id'])['peers'][0]
        return peer['channels'][0]['htlcs'] == []

    wait_for(no_pending_htlcs)

    chan = l2.rpc.listpeers(l3.info['id'])['peers'][0]['channels'][0]
    pprint(chan)
    assert(chan['spendable_msatoshi'] < amt)

    # Get (l2, l5) so we can exclude it when routing from l1 to l4
    peer = l2.rpc.listpeers(l5.info['id'])['peers'][0]
    scid = peer['channels'][0]['short_channel_id']

    # The actual invoice that l1 will attempt to pay to l4, and that will be
    # larger than the current capacity of (l2, l3) so it triggers a
    # rebalancing.
    inv = l4.rpc.invoice(amt, "test", "test")

    # Now wait for gossip to settle and l1 to learn the topology so it can
    # then route the payment. We do this now since we already did what we
    # could without this info
    wait_for(lambda: len(l1.rpc.listchannels()['channels']) == 2*len(channels))

    route = l1.rpc.getroute(node_id=l4.info['id'], msatoshi=amt, riskfactor=1,
                            exclude=[scid + '/0', scid + '/1'])['route']

    # This will fail without the plugin doing a rebalancing.
    l1.rpc.sendpay(route, inv['payment_hash'])
    pprint(l1.rpc.waitsendpay(inv['payment_hash']))
