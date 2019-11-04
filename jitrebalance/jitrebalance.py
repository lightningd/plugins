#!/usr/bin/env python3
from math import ceil
from pprint import pprint
from pyln.client import Plugin, Millisatoshi
import binascii
import hashlib
import secrets
import time

plugin = Plugin()


def get_circular_route(route, scid):
    pass


@plugin.async_hook("htlc_accepted")
def on_htlc_accepted(htlc, onion, plugin, request, **kwargs):
    plugin.log("Got an incoming HTLC htlc={}, onion={}".format(htlc, onion))

    # The HTLC might be a rebalance we ourselves initiated, better check
    # against the list of pending ones.
    rebalance = plugin.rebalances.get(htlc['payment_hash'])
    if rebalance is not None:
        # Settle the rebalance, before settling the request that initiated the
        # rebalance.
        request.set_result({
            "result": "resolve",
            "payment_key": rebalance['payment_key']
        })

        # Now wait for it to settle correctly
        # TODO Maybe be a bit smarter than having a fixed timeout here?
        time.sleep(1)

        rebalance['request'].set_result({"result": "continue"})
        return

    # Check to see if the next channel has sufficient capacity
    scid = onion['per_hop_v0']['short_channel_id']

    # Are we the destination? Then there's nothing to do. Continue.
    if scid == '0x0x0':
        request.set_result({"result": "continue"})
        return

    # Locate the channel + direction that would be the next in the path
    peers = plugin.rpc.listpeers()['peers']

    chan = None
    peer = None
    for p in peers:
        for c in p['channels']:
            if c['short_channel_id'] == scid:
                chan = c
                peer = p

    # Check if the channel is active and routable, otherwise there's little
    # point in even trying
    if not peer['connected'] or chan['state'] != "CHANNELD_NORMAL":
        request.set_result({"result": "continue"})
        return

    # Need to consider who the funder is, since they are paying the fees.
    # TODO If we are the funder we need to take the cost of an HTLC into
    # account as well.
    #funder = chan['msatoshi_to_us_max'] == chan['msatoshi_total']

    forward_amt = Millisatoshi(onion['per_hop_v0']['forward_amount'])
    incoming_amt = Millisatoshi(htlc['amount'])
    fee = incoming_amt - forward_amt
    pprint(fee)
    # Compute the amount we need to rebalance, give us a bit of breathing room
    # while we're at it (25% more rebalancing than strictly necessary) so we
    # don't end up with a completely unbalanced channel right away again, and
    # to account for a bit of fuzziness when it comes to dipping into the
    # reserve.
    amt = ceil(int(forward_amt - chan['spendable_msat']) * 1.25)

    # If we have a higher balance than is required we don't need to rebalance,
    # just stop here.
    if amt <= 0:
        request.set_result({"result": "continue"})
        return

    # Compute the last leg of the route first, so we know the parameters to
    # traverse that last edge.
    reverse_chan = plugin.rpc.listchannels(scid)['channels']
    assert(len(reverse_chan) == 2)
    reverse_chan = [
        c for c in reverse_chan if c['channel_flags'] != chan['direction']
    ][0]

    if reverse_chan is None:
        print("Could not compute parameters for the last hop")
        request.set_result({"result": "continue"})
        return

    last_amt = ceil(float(amt) +
                    float(amt) * reverse_chan['fee_per_millionth'] / 10**6 +
                    reverse_chan['base_fee_millisatoshi'])
    last_cltv = 9 + reverse_chan['delay']

    # Exclude the channel we are trying to rebalance when searching for a
    # path. We will manually append it to the route and bump the other
    # parameters so it can be used afterwards
    exclusions = [
        "{scid}/{direction}".format(scid=scid, direction=chan['direction'])
    ]

    route = plugin.rpc.getroute(
        node_id=peer['id'],
        msatoshi=last_amt,
        riskfactor=1,
        exclude=exclusions,
        cltv=last_cltv,
    )['route']

    # Append the last hop we computed manually above
    route += [{
        'id': plugin.node_id,
        'channel': scid,
        'direction': chan['direction'],
        'msatoshi': amt,
        'amount_msat': '{}msat'.format(amt),
        'delay': 9
    }]

    # We're about to initiate a rebalancing, we'd better remember how we can
    # settle it once we see it back here.

    payment_key = secrets.token_bytes(32)
    payment_hash = hashlib.sha256(payment_key).hexdigest()
    plugin.rebalances[payment_hash] = {
        "payment_key": binascii.hexlify(payment_key).decode('ASCII'),
        "payment_hash": payment_hash,
        "request": request,
    }

    # After all this work we're finally in a position to judge whether a
    # rebalancing is worth it at all. The rebalancing is considered worth it
    # if the fees we're about to pay are less than or equal to the fees we get
    # out of forwarding the payment.

    plugin.log("Sending rebalance request using payment_hash={}".format(
        payment_hash
    ))
    plugin.rpc.sendpay(route, payment_hash)


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("jitrebalance.py initializing {}".format(configuration))
    plugin.node_id = plugin.rpc.getinfo()['id']

    # Set of currently active rebalancings, keyed by their payment_hash
    plugin.rebalances = {}


plugin.run()
