#!/usr/bin/env python3
import random
import time
from pyln.client import Plugin, Millisatoshi, RpcError


plugin = Plugin()
# Our amount and the total amount in each of our channel, indexed by scid
plugin.adj_balances = {}
# Cache to avoid loads of calls to getinfo
plugin.our_node_id = None
# Users can configure this
plugin.update_threshold = 0.05


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

        # reset to normal fees if imbalance is not high enough
        if (percentage > plugin.imbalance and percentage < 1 - plugin.imbalance):
            plugin.rpc.setchannelfee(scid)  # applies default values
            plugin.log("Set default fees as imbalance is too low: {}".format(scid))
            return

        # Only update on substantial balance moves to avoid flooding, and add
        # some pseudo-randomness to avoid too easy channel balance probing
        update_threshold = plugin.update_threshold
        if not plugin.deactivate_fuzz:
            update_threshold += random.uniform(-0.015, 0.015)

        if (last_percentage is None
                or abs(last_percentage - percentage) > update_threshold):
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
        # We might have multiple channel entries ! Eg if one was just closed
        # and reopened.
        for chan in peer["channels"]:
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
            # Pseudo-randomly add some hysterisis to the update
            if not plugin.deactivate_fuzz and random.randint(0, 9) == 9:
                time.sleep(random.randint(0, 5))
            maybe_adjust_fees(plugin, [in_scid, out_scid])
        except Exception as e:
            plugin.log("Adjusting fees: " + str(e), level="error")


@plugin.init()
def init(options: dict, configuration: dict, plugin: Plugin, **kwargs):
    plugin.our_node_id = plugin.rpc.getinfo()["id"]
    plugin.deactivate_fuzz = options.get("feeadjuster-deactivate-fuzz", False)
    plugin.update_threshold = float(options.get("feeadjuster-threshold", "0.05"))
    plugin.imbalance = float(options.get("feeadjuster-imbalance", 0.5))
    config = plugin.rpc.listconfigs()
    plugin.adj_basefee = config["fee-base"]
    plugin.adj_ppmfee = config["fee-per-satoshi"]

    # normalize the imbalance percentage value to 0%-50%
    if plugin.imbalance < 0 or plugin.imbalance > 1:
        raise ValueError("feeadjuster-imbalance must be between 0 and 1.")
    if plugin.imbalance > 0.5:
        plugin.imbalance = 1 - plugin.imbalance

    plugin.log("Plugin feeadjuster initialized ({} base / {} ppm) with an "
               "imbalance of {}%/{}%".format(plugin.adj_basefee,
                                           plugin.adj_ppmfee,
                                           int(100*plugin.imbalance),
                                           int(100*(1-plugin.imbalance))))


plugin.add_option(
    "feeadjuster-deactivate-fuzz",
    False,
    "Deactivate update threshold randomization and hysterisis.",
    "flag"
)
plugin.add_option(
    "feeadjuster-threshold",
    "0.05",
    "Channel balance update threshold at which to trigger an update. "
    "Note: it's also fuzzed by 1.5%",
    "string"
)
plugin.add_option(
    "feeadjuster-imbalance",
    "0.5",
    "Ratio at which channel imbalance the feeadjuster should start acting. "
    "Default: 0.5 (always). Set higher or lower values to limit feeadjuster's "
    "activity to more imbalanced channels. "
    "E.g. 0.3 for '70/30'% or 0.6 for '40/60'%.",
    "string"
)
plugin.run()
