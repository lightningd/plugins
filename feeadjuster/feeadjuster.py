#!/usr/bin/env python3
from concurrent.futures import ThreadPoolExecutor
from pyln.client import Plugin, Millisatoshi, RpcError


plugin = Plugin()
# Our amount and the total amount in each of our channel, indexed by scid
plugin.adj_balances = {}
# Make requests to lightningd in parallel
plugin.adj_thread_pool = None
# Cache to avoid loads of calls to getinfo
plugin.our_node_id = None


def get_ratio(our_percentage):
    """
    Basic algorithm: the farther we are from the optimal case, the more we
    bump/lower.
    """
    return 50**(0.5 - our_percentage)


def get_fees(plugin: Plugin, scid: str):
    for half in plugin.rpc.listchannels(scid)["channels"]:
        if plugin.our_node_id in half["source"]:
            return (half["base_fee_millisatoshi"], half["fee_per_millionth"])

    # Note: the half may not be present, so this may actually return None!


def maybe_adjust_fees(plugin: Plugin, scids: list):
    for scid in scids:
        # FIXME: set a threshold to avoid flooding!
        if True:
            # FIXME: it's exponential! We need to cache the startup
            # fees instead of always factorising the updated ones.
            fees = get_fees(plugin, scid)
            if fees is None:
                return

            our = plugin.adj_balances[scid]["our"]
            total = plugin.adj_balances[scid]["total"]
            ratio = get_ratio(our / total)
            try:
                plugin.rpc.setchannelfee(scid, int(fees[0] * ratio),
                                         int(fees[1] * ratio))
                plugin.log("Adjusted fees of {} with a ratio of {}"
                           .format(scid, ratio))
            except RpcError as e:
                plugin.log(str(e), level="warn")


def get_chan(plugin: Plugin, scid: str):
    for peer in plugin.rpc.listpeers()["peers"]:
        if len(peer["channels"]) == 0:
            continue
        chan = peer["channels"][0]
        if "short_channel_id" not in chan:
            continue
        if chan["short_channel_id"] == scid:
            return chan


def maybe_add_new_balances(plugin: Plugin, scids: list):
    for scid in scids:
        if scid not in plugin.adj_balances:
            # At this point we could call listchannels and pass the scid as
            # argument, and deduce the peer id (!our_id). But -as unlikely as
            # it is- we may not find it in our gossip (eg some corruption of
            # the gossip_store occured just before the forwarding event).
            # However, it MUST be present in a listpeers() entry.
            chan = get_chan(plugin, scid)
            assert chan is not None

            plugin.adj_balances[scid] = {
                "our": int(chan["to_us_msat"]),
                "total": int(chan["total_msat"])
            }


def threaded_forward_event(plugin: Plugin, forward_event: dict):
    in_scid = forward_event["in_channel"]
    out_scid = forward_event["out_channel"]
    maybe_add_new_balances(plugin, [in_scid, out_scid])

    plugin.adj_balances[in_scid]["our"] += forward_event["in_msatoshi"]
    plugin.adj_balances[out_scid]["our"] -= forward_event["out_msatoshi"]
    maybe_adjust_fees(plugin, [in_scid, out_scid])


@plugin.subscribe("forward_event")
def forward_event(plugin: Plugin, forward_event: dict, **kwargs):
    if forward_event["status"] == "settled":
        plugin.adj_thread_pool.submit(threaded_forward_event,
                                      plugin, forward_event)


@plugin.init()
def init(options: dict, configuration: dict, plugin: Plugin, **kwargs):
    plugin.our_node_id = plugin.rpc.getinfo()["id"]
    plugin.adj_thread_pool = ThreadPoolExecutor(
        max_workers=int(options["feeadjuster-par"])
    )

    for peer in plugin.rpc.listpeers()["peers"]:
        if len(peer["channels"]) == 0:
            continue
        chan = peer["channels"][0]
        if "short_channel_id" not in chan:
            continue
        if chan["state"] != "CHANNELD_NORMAL":
            continue

    plugin.log("Plugin feeadjuster initialized with {} threads"
               .format(options["feeadjuster-par"]))


plugin.add_option("feeadjuster-par", 8, "Maximum number of threads launched to"
                  "adjust fees", opt_type="int")
plugin.run()
