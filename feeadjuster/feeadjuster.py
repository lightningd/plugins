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


def get_ratio_soft(our_percentage):
    """
    Basic algorithm: lesser difference than default
    """
    our_percentage = min(1, max(0, our_percentage))
    return 10**(0.5 - our_percentage)


def get_ratio(our_percentage):
    """
    Basic algorithm: the farther we are from the optimal case, the more we
    bump/lower.
    """
    our_percentage = min(1, max(0, our_percentage))
    return 50**(0.5 - our_percentage)


def get_ratio_hard(our_percentage):
    """
    Return value is between 0 and 20: 0 -> 20; 0.5 -> 1; 1 -> 0
    """
    our_percentage = min(1, max(0, our_percentage))
    return 100**(0.5 - our_percentage) * (1 - our_percentage) * 2


def get_chan_fees(plugin: Plugin, scid: str):
    channels = plugin.rpc.listchannels(scid)["channels"]
    for ch in channels:
        if ch["source"] == plugin.our_node_id:
            return { "base_fee_millisatoshi": ch["base_fee_millisatoshi"],
                     "fee_per_millionth": ch["fee_per_millionth"] }


def maybe_setchannelfee(plugin: Plugin, scid: str, base: int, ppm: int):
    fees = get_chan_fees(plugin, scid)
    if fees is None or base == fees["base_fee_millisatoshi"] and ppm == fees["fee_per_millionth"]:
        return False
    try:
        plugin.rpc.setchannelfee(scid, base, ppm)
        return True
    except RpcError as e:
        plugin.log("Could not adjust fees for channel {}: '{}'".format(scid, e), level="warn")
    return False


def maybe_adjust_fees(plugin: Plugin, scids: list):
    channels_adjusted = 0
    for scid in scids:
        our = plugin.adj_balances[scid]["our"]
        total = plugin.adj_balances[scid]["total"]
        percentage = our / total
        last_percentage = plugin.adj_balances[scid].get("last_percentage")

        # reset to normal fees if imbalance is not high enough
        if (percentage > plugin.imbalance and percentage < 1 - plugin.imbalance):
            if maybe_setchannelfee(plugin, scid, plugin.adj_basefee, plugin.adj_ppmfee):
                plugin.log("Set default fees as imbalance is too low: {}".format(scid))
                plugin.adj_balances[scid]["last_percentage"] = percentage
                channels_adjusted += 1
            continue

        # Only update on substantial balance moves to avoid flooding, and add
        # some pseudo-randomness to avoid too easy channel balance probing
        update_threshold = plugin.update_threshold
        if not plugin.deactivate_fuzz:
            update_threshold += random.uniform(-0.015, 0.015)
        if (last_percentage is not None
                and abs(last_percentage - percentage) < update_threshold):
            continue

        ratio = plugin.get_ratio(percentage)
        if maybe_setchannelfee(plugin, scid, int(plugin.adj_basefee * ratio),
                               int(plugin.adj_ppmfee * ratio)):
            plugin.log("Adjusted fees of {} with a ratio of {}"
                       .format(scid, ratio))
            plugin.adj_balances[scid]["last_percentage"] = percentage
            channels_adjusted += 1
    return channels_adjusted


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


@plugin.method("feeadjust")
def feeadjust(plugin: Plugin):
    """Adjust fees for all existing channels.

    This method is automatically called in plugin init, or can be called manually after a successful payment.
    Otherwise, the plugin keeps the fees up-to-date.
    """
    peers = plugin.rpc.listpeers()["peers"]
    channels_adjusted = 0
    for peer in peers:
        for chan in peer["channels"]:
            if chan["state"] == "CHANNELD_NORMAL":
                scid = chan["short_channel_id"];
                plugin.adj_balances[scid] = {
                    "our": int(chan["to_us_msat"]),
                    "total": int(chan["total_msat"])
                }
                channels_adjusted += maybe_adjust_fees(plugin, [scid])
    msg = f"{channels_adjusted} channels adjusted"
    plugin.log(msg)
    return msg


@plugin.init()
def init(options: dict, configuration: dict, plugin: Plugin, **kwargs):
    plugin.our_node_id = plugin.rpc.getinfo()["id"]
    plugin.deactivate_fuzz = options.get("feeadjuster-deactivate-fuzz", False)
    plugin.update_threshold = float(options.get("feeadjuster-threshold", "0.05"))
    plugin.imbalance = float(options.get("feeadjuster-imbalance", 0.5))
    plugin.get_ratio = get_ratio
    if options.get("feeadjuster-adjustment-method", "default") == "soft":
        plugin.get_ratio = get_ratio_soft
    if options.get("feeadjuster-adjustment-method", "default") == "hard":
        plugin.get_ratio = get_ratio_hard
    config = plugin.rpc.listconfigs()
    plugin.adj_basefee = config["fee-base"]
    plugin.adj_ppmfee = config["fee-per-satoshi"]

    # normalize the imbalance percentage value to 0%-50%
    if plugin.imbalance < 0 or plugin.imbalance > 1:
        raise ValueError("feeadjuster-imbalance must be between 0 and 1.")
    if plugin.imbalance > 0.5:
        plugin.imbalance = 1 - plugin.imbalance

    plugin.log("Plugin feeadjuster initialized ({} base / {} ppm) with an "
               "imbalance of {}%/{}%, update_threshold: {}, deactivate_fuzz: {}, adjustment_method: {}"
               .format(plugin.adj_basefee,
                   plugin.adj_ppmfee,
                   int(100*plugin.imbalance),
                   int(100*(1-plugin.imbalance)),
                   plugin.update_threshold,
                   plugin.deactivate_fuzz,
                   plugin.get_ratio.__name__))
    feeadjust(plugin)


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
    "feeadjuster-adjustment-method",
    "default",
    "Adjustment method to calculate channel fee"
    "Can be 'default', 'soft' for less difference or 'hard' for higher difference"
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
