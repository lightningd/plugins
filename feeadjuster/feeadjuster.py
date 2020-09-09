#!/usr/bin/env python3
from concurrent.futures import ThreadPoolExecutor
from pyln.client import Plugin, Millisatoshi, RpcError


plugin = Plugin()
# Our amount and the total amount in each of our channel, indexed by scid
plugin.adj_balances = {}
# Cache to avoid loads of calls to getinfo
plugin.our_node_id = None


def get_ratio(our_percentage):
    """
    Basic algorithm: the farther we are from the optimal case, the more we
    bump/lower.
    """
    return 50**(0.5 - our_percentage)


def maybe_adjust_fees(plugin: Plugin, scids: list):
    for scid in scids:
        our = plugin.adj_balances[scid]["our"]
        total = plugin.adj_balances[scid]["total"]
        percentage = our / total
        last_percentage = plugin.adj_balances[scid].get("last_percentage")

        # Only update on substantial balance moves to avoid flooding
        if last_percentage is None or abs(last_percentage - percentage) > 0.05:
            ratio = get_ratio(percentage)
            try:
                plugin.rpc.setchannelfee(scid, int(plugin.adj_basefee * ratio),
                                         int(plugin.adj_ppmfee * ratio))
                plugin.log("Adjusted fees of {} with a ratio of {}"
                           .format(scid, ratio))
                plugin.adj_balances[scid]["last_percentage"] = percentage
            except RpcError as e:
                plugin.log("Could not adjust fees for channel {}: '{}'"
                           .format(scid, e), level="warn")


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


@plugin.subscribe("forward_event")
def forward_event(plugin: Plugin, forward_event: dict, **kwargs):
    if forward_event["status"] == "settled":
        in_scid = forward_event["in_channel"]
        out_scid = forward_event["out_channel"]
        maybe_add_new_balances(plugin, [in_scid, out_scid])

        plugin.adj_balances[in_scid]["our"] += forward_event["in_msatoshi"]
        plugin.adj_balances[out_scid]["our"] -= forward_event["out_msatoshi"]
        try:
            maybe_adjust_fees(plugin, [in_scid, out_scid])
        except Exception as e:
            plugin.log("Adjusting fees: " + str(e), level="error")


@plugin.init()
def init(options: dict, configuration: dict, plugin: Plugin, **kwargs):
    plugin.our_node_id = plugin.rpc.getinfo()["id"]
    config = plugin.rpc.listconfigs()
    plugin.adj_basefee = config["fee-base"]
    plugin.adj_ppmfee = config["fee-per-satoshi"]

    for peer in plugin.rpc.listpeers()["peers"]:
        if len(peer["channels"]) == 0:
            continue
        chan = peer["channels"][0]
        if "short_channel_id" not in chan:
            continue
        if chan["state"] != "CHANNELD_NORMAL":
            continue

    plugin.log("Plugin feeadjuster initialized ({} base / {} ppm)"
               .format(plugin.adj_basefee, plugin.adj_ppmfee))


plugin.run()
