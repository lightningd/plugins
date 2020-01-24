#!/usr/bin/python3
"""
author: Rene Pickhardt (rene.m.pickhardt@ntnu.no)
Date: 24.1.2020
License: MIT

This plugin helps you to construct a route object (to be used with `sendpay`)
which goes over a sequence of node ids. If all these nodeids are on a path of
payment channels an onion following this path will be constructed. In the case
of missing channels `lightning-cli getroute` is invoked to find partial routes.

This plugin can be used to create circular onions or to send payments along
specific paths if that is necessary (as long as the paths provide enough
liquidity).

I guess this plugin could also be used to simulate the behaviour of trampoline
payments.

And of course I imagine you the reader of this message will find even more
creative ways of using it.

=== Support:

If you like my work consider a donation at https://patreon.com/renepickhardt
or https://tallyco.in/s/lnbook

"""

from pyln.client import Plugin
from pyln.client import RpcError
import itertools


plugin = Plugin(autopatch=True)


@plugin.method(
    "getfixedroute",
    long_desc="""
Returns a route object to be used in send pay over a fixed set of nodes
"""
)
def getfixedroute(plugin, amount, nodes):
    """Construct a fixed route over a list of node ids.

    If channels exist between consecutive nodes these channels will be used.
    Otherwise `lightning-cli getroute` will be invoked to find partial routes.

    """
    delay = 9
    fees = 0
    result = []

    def pairs(iterable):
        x, y = itertools.tee(iterable)
        next(y, None)
        return zip(x, y)

    for src, dest in reversed(list(pairs(nodes))):
        amount = amount + fees
        key = "{}:{}".format(src, dest)
        if key not in plugin.channels:
            try:
                route = plugin.rpc.getroute(
                    node_id=dest, msatoshi=amount, riskfactor=1, cltv=delay,
                    fromid=src
                )["route"]
            except RpcError as exc:
                raise ValueError((
                    "could not compute route between waypoints {src} and "
                    "{dest}: {e}"
                ).format(src=src, dest=dest, e=exc))

            for e in reversed(route):
                result.append(e)

            key = "{}:{}".format(src, route[0]["id"])
            chan = plugin.channels[key]

            base = chan["base_fee_millisatoshi"]
            prop = chan["fee_per_millionth"]

            fees = base + amount * prop / 10**6
            delay = result[-1]["delay"] + chan["delay"]

        else:
            chan = plugin.channels[key]
            # https://github.com/ElementsProject/lightning/blob/edbcb6/gossipd/routing.h#L253

            direction = 0
            # I guess the following reverses the definition with the DER
            # encoding of channels for all my tests the results where the same
            # as in getroute but I am not sure if this is actually
            # correct. please can someone verify and remove this message:
            # https://github.com/ElementsProject/lightning/blob/edbcb6/gossipd/routing.h#L56
            if dest < src:
                direction = 1

            # https://github.com/ElementsProject/lightning/blob/edbcb6/gossipd/routing.c#L381
            style = "legacy"

            # https://github.com/ElementsProject/lightning/blob/edbcb6f/gossipd/routing.c#L2526
            # and :
            # https://github.com/lightningnetwork/lightning-rfc/blob/master/09-features.md
            features = int(plugin.nodes[dest]["globalfeatures"], 16)
            if features & 0x01 << 8 != 0 or features & 0x01 << 9 != 0:
                style = "tlv"
            entry = {
                "id": dest,
                "channel": chan["short_channel_id"],
                "direction": direction,
                "msatoshi": amount,
                "amount_msat": "{}msat".format(amount),
                "delay": delay,
                "style": style
            }
            result.append(entry)

            base = chan["base_fee_millisatoshi"]
            prop = chan["fee_per_millionth"]

            fees = base + amount * prop / 10**6
            delay = delay + chan["delay"]

        fees = int(fees)
    result = list(reversed(result))

    # id, chanel, direction, msatoshi, amount_msat, delay, style
    return {"route": result}


@plugin.method(
    "getfixedroute_purge",
    long_desc="purges the index of the gossip store"
)
def refresh_gossip_info(plugin):
    """
    purges the index gossip store.
    """
    channels = plugin.rpc.listchannels()["channels"]

    for chan in channels:
        key = "{}:{}".format(chan["source"], chan["destination"])
        plugin.channels[key] = chan

    for u in plugin.rpc.listnodes()["nodes"]:
        plugin.nodes[u["nodeid"]] = u

    return {"result": "successfully reindexed the gossip store."}


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("Plugin fixroute_pay registered")
    refresh_gossip_info(plugin)


plugin.run()
