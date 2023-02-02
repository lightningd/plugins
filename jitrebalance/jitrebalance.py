#!/usr/bin/env python3
from math import ceil
from pyln.client import Plugin, Millisatoshi, RpcError
import binascii
import hashlib
import secrets
import threading
import time

plugin = Plugin()


def get_reverse_chan(scid, chan):
    for c in plugin.rpc.listchannels(scid)['channels']:
        if c['channel_flags'] != chan['direction']:
            return c

    return None


def get_circular_route(scid, chan, amt, peer, exclusions, request):
    """Compute a circular route with `scid` as last leg.

    """
    # Compute the last leg of the route first, so we know the parameters to
    # traverse that last edge.
    reverse_chan = get_reverse_chan(scid, chan)

    if reverse_chan is None:
        plugin.log("Could not compute parameters for the last hop")
        return None

    last_amt = ceil(float(amt) +
                    float(amt) * reverse_chan['fee_per_millionth'] / 10**6 +
                    reverse_chan['base_fee_millisatoshi'])
    last_cltv = 9 + reverse_chan['delay']

    try:
        route = plugin.rpc.getroute(
            node_id=peer['id'],
            amount_msat=last_amt,
            riskfactor=1,
            exclude=exclusions,
            cltv=last_cltv,
        )['route']

        # Append the last hop we computed manually above
        route += [{
            'id': plugin.node_id,
            'channel': scid,
            'direction': chan['direction'],
            'amount_msat': '{}msat'.format(amt),
            'delay': 9
        }]

        return route
    except RpcError:
        plugin.log("Could not get a route, no remaining one? Exclusions : {}"
                   .format(exclusions))
        return None


def try_rebalance(scid, chan, amt, peer, request):
    # Exclude the channel we are trying to rebalance when searching for a
    # path. We will manually append it to the route and bump the other
    # parameters so it can be used afterwards
    exclusions = [
        "{scid}/{direction}".format(scid=scid, direction=chan['direction'])
    ]

    # Try as many routes as possible before the timeout expires
    stop_time = int(time.time()) + plugin.rebalance_timeout
    while int(time.time()) <= stop_time:
        route = get_circular_route(scid, chan, amt, peer, exclusions, request)
        # We exhausted all the possibilities, Game Over
        if route is None:
            request.set_result({"result": "continue"})
            return

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
        plugin.log("Sending rebalance request using payment_hash={}, route={}".format(
            payment_hash, route
        ))
        try:
            plugin.rpc.sendpay(route, payment_hash)
            # If the attempt is successful, we acknowledged it on the
            # receiving end (a couple of line above), so we leave it dangling
            # here.
            if (plugin.rpc.waitsendpay(payment_hash).get("status")
                    == "complete"):
                plugin.log("Succesfully re-filled outgoing capacity in {},"
                           "payment_hash={}".format(scid, payment_hash))
            return
        except RpcError as e:
            if not "data" in e.error:
                raise e
            data = e.error['data']
            # The erring_channel field can not be present (shouldn't happen) or
            # can be "0x0x0"
            erring_channel = data.get('erring_channel', '0x0x0')
            if erring_channel != '0x0x0':
                if erring_channel == scid:
                    break
                erring_direction = data['erring_direction']
                exclusions.append("{}/{}".format(erring_channel,
                                                 erring_direction))
                plugin.log("Excluding {} due to a failed attempt"
                           .format(erring_channel))

    plugin.log("Timed out while trying to rebalance")
    request.set_result({"result": "continue"})


def get_peer_and_channel(peers, scid):
    """Look for the channel identified by {scid} in our list of {peers}"""
    for peer in peers:
        channels = []
        if 'channels' in peer:
            channels = peer["channels"]
        elif 'num_channels' in peer and peer['num_channels'] > 0:
            channels = plugin.rpc.listpeerchannels(peer["id"])["channels"]
        for channel in channels:
            if channel.get("short_channel_id") == scid:
                return (peer, channel)
    return (None, None)


@plugin.async_hook("htlc_accepted")
def on_htlc_accepted(htlc, onion, plugin, request, **kwargs):
    plugin.log("Got an incoming HTLC htlc={}".format(htlc))

    # The HTLC might be a rebalance we ourselves initiated, better check
    # against the list of pending ones.
    rebalance = plugin.rebalances.get(htlc['payment_hash'], None)
    if rebalance is not None:
        # Settle the rebalance, before settling the request that initiated the
        # rebalance.
        request.set_result({
            "result": "resolve",
            "payment_key": rebalance['payment_key']
        })

        # Now wait for it to settle correctly
        plugin.rpc.waitsendpay(htlc['payment_hash'])

        rebalance['request'].set_result({"result": "continue"})

        # Clean up our stash of active rebalancings.
        del plugin.rebalances[htlc['payment_hash']]
        return

    # Check to see if the next channel has sufficient capacity
    scid = onion['short_channel_id'] if 'short_channel_id' in onion else '0x0x0'

    # Are we the destination? Then there's nothing to do. Continue.
    if scid == '0x0x0':
        request.set_result({"result": "continue"})
        return

    # Locate the channel + direction that would be the next in the path
    peers = plugin.rpc.listpeers()['peers']

    peer, chan = get_peer_and_channel(peers, scid)
    if peer is None or chan is None:
        return

    # Check if the channel is active and routable, otherwise there's little
    # point in even trying
    if not peer['connected'] or chan['state'] != "CHANNELD_NORMAL":
        request.set_result({"result": "continue"})
        return

    # Need to consider who the funder is, since they are paying the fees.
    # TODO If we are the funder we need to take the cost of an HTLC into
    # account as well.
    # funder = chan['msatoshi_to_us_max'] == chan['msatoshi_total']
    forward_amt = Millisatoshi(onion['forward_msat'])

    # If we have enough capacity just let it through now. Otherwise the
    # Millisatoshi raises an error for negative amounts in the calculation
    # below.
    if forward_amt < chan['spendable_msat']:
        request.set_result({"result": "continue"})
        return

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

    t = threading.Thread(target=try_rebalance, args=(scid, chan, amt, peer, request))
    t.daemon = True
    t.start()


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("jitrebalance.py initializing {}".format(configuration))

    plugin.node_id = plugin.rpc.getinfo()['id']
    plugin.rebalance_timeout = int(options.get("jitrebalance-try-timeout"))
    # Set of currently active rebalancings, keyed by their payment_hash
    plugin.rebalances = {}


plugin.add_option(
    "jitrebalance-try-timeout",
    60,
    "Number of seconds before we stop trying to rebalance a channel.",
    opt_type="int"
)


plugin.run()
