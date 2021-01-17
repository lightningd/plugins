#!/usr/bin/env python3
import random
import time
from pyln.client import Plugin, Millisatoshi, RpcError
from threading import Lock


plugin = Plugin()
# Our amount and the total amount in each of our channel, indexed by scid
plugin.adj_balances = {}
# Cache to avoid loads of calls to getinfo
plugin.our_node_id = None
# Users can configure this
plugin.update_threshold = 0.05
# forward_event must wait for init
plugin.mutex = Lock()
plugin.mutex.acquire()


def get_adjusted_percentage(plugin: Plugin, scid: str):
    """
    For big channels, there may be a wide range where the liquidity is just okay.
    Note: if big_enough_liquidity is greater than {total} * 2
          then percentage is actually {our} / {total}, as it was before
    """
    channel = plugin.adj_balances[scid]
    if plugin.big_enough_liquidity == Millisatoshi(0):
        return channel["our"] / channel["total"]
    min_liquidity = min(channel["total"] / 2, int(plugin.big_enough_liquidity))
    theirs = channel["total"] - channel["our"]
    if channel["our"] >= min_liquidity and theirs >= min_liquidity:
        # the liquidity is just okay
        return 0.5
    if channel["our"] < min_liquidity:
        # our liquidity is too low
        return channel["our"] / min_liquidity / 2
    # their liquidity is too low
    return (min_liquidity - theirs) / min_liquidity / 2 + 0.5


def get_ratio_soft(our_percentage):
    """
    Basic algorithm: lesser difference than default
    """
    return 10**(0.5 - our_percentage)


def get_ratio(our_percentage):
    """
    Basic algorithm: the farther we are from the optimal case, the more we
    bump/lower.
    """
    return 50**(0.5 - our_percentage)


def get_ratio_hard(our_percentage):
    """
    Return value is between 0 and 20: 0 -> 20; 0.5 -> 1; 1 -> 0
    """
    return 100**(0.5 - our_percentage) * (1 - our_percentage) * 2


def get_chan_fees(plugin: Plugin, scid: str):
    channels = plugin.rpc.listchannels(scid)["channels"]
    for ch in channels:
        if ch["source"] == plugin.our_node_id:
            return {"base_fee_millisatoshi": ch["base_fee_millisatoshi"],
                    "fee_per_millionth": ch["fee_per_millionth"]}


def maybe_setchannelfee(plugin: Plugin, scid: str, base: int, ppm: int):
    fees = get_chan_fees(plugin, scid)
    if fees is None or base == fees["base_fee_millisatoshi"] and ppm == fees["fee_per_millionth"]:
        return False
    try:
        plugin.rpc.setchannelfee(scid, base, ppm)
        return True
    except RpcError as e:
        plugin.log(f"Could not adjust fees for channel {scid}: '{e}'", level="error")
    return False


def significant_update(plugin: Plugin, scid: str):
    channel = plugin.adj_balances[scid]
    last_liquidity = channel.get("last_liquidity")
    if last_liquidity is None:
        return True
    # Only update on substantial balance moves to avoid flooding, and add
    # some pseudo-randomness to avoid too easy channel balance probing
    update_threshold = plugin.update_threshold
    update_threshold_abs = int(plugin.update_threshold_abs)
    if not plugin.deactivate_fuzz:
        update_threshold += random.uniform(-0.015, 0.015)
        update_threshold_abs += update_threshold_abs * random.uniform(-0.015, 0.015)
    last_percentage = last_liquidity / channel["total"]
    percentage = channel["our"] / channel["total"]
    if (abs(last_percentage - percentage) > update_threshold
            or abs(last_liquidity - channel["our"]) > update_threshold_abs):
        return True
    return False


def maybe_adjust_fees(plugin: Plugin, scids: list):
    channels_adjusted = 0
    for scid in scids:
        our = plugin.adj_balances[scid]["our"]
        total = plugin.adj_balances[scid]["total"]
        percentage = our / total

        # reset to normal fees if imbalance is not high enough
        if (percentage > plugin.imbalance and percentage < 1 - plugin.imbalance):
            if maybe_setchannelfee(plugin, scid, plugin.adj_basefee, plugin.adj_ppmfee):
                plugin.log(f"Set default fees as imbalance is too low: {scid}")
                plugin.adj_balances[scid]["last_liquidity"] = our
                channels_adjusted += 1
            continue

        if not significant_update(plugin, scid):
            continue

        percentage = get_adjusted_percentage(plugin, scid)
        assert 0 <= percentage and percentage <= 1
        ratio = plugin.get_ratio(percentage)
        if maybe_setchannelfee(plugin, scid, int(plugin.adj_basefee * ratio),
                               int(plugin.adj_ppmfee * ratio)):
            plugin.log(f"Adjusted fees of {scid} with a ratio of {ratio}")
            plugin.adj_balances[scid]["last_liquidity"] = our
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
    if not plugin.forward_event_subscription:
        return
    plugin.mutex.acquire(blocking=True)
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
    plugin.mutex.release()


@plugin.method("feeadjust")
def feeadjust(plugin: Plugin):
    """Adjust fees for all existing channels.

    This method is automatically called in plugin init, or can be called manually after a successful payment.
    Otherwise, the plugin keeps the fees up-to-date.
    """
    plugin.mutex.acquire(blocking=True)
    peers = plugin.rpc.listpeers()["peers"]
    channels_adjusted = 0
    for peer in peers:
        for chan in peer["channels"]:
            if chan["state"] == "CHANNELD_NORMAL":
                scid = chan["short_channel_id"]
                plugin.adj_balances[scid] = {
                    "our": int(chan["to_us_msat"]),
                    "total": int(chan["total_msat"])
                }
                channels_adjusted += maybe_adjust_fees(plugin, [scid])
    msg = f"{channels_adjusted} channels adjusted"
    plugin.log(msg)
    plugin.mutex.release()
    return msg


@plugin.method("feeadjustertoggle")
def feeadjustertoggle(plugin: Plugin, value: bool = None):
    """Activates/Deactivates automatic fee updates for forward events.

    The status will be set to value.
    """
    msg = {"forward_event_subscription": {"previous": plugin.forward_event_subscription}}
    if value is None:
        plugin.forward_event_subscription = not plugin.forward_event_subscription
    else:
        plugin.forward_event_subscription = bool(value)
    msg["forward_event_subscription"]["current"] = plugin.forward_event_subscription
    return msg


@plugin.init()
def init(options: dict, configuration: dict, plugin: Plugin, **kwargs):
    plugin.our_node_id = plugin.rpc.getinfo()["id"]
    plugin.deactivate_fuzz = options.get("feeadjuster-deactivate-fuzz")
    plugin.forward_event_subscription = not options.get("feeadjuster-deactivate-fee-update")
    plugin.update_threshold = float(options.get("feeadjuster-threshold"))
    plugin.update_threshold_abs = Millisatoshi(options.get("feeadjuster-threshold-abs"))
    plugin.big_enough_liquidity = Millisatoshi(options.get("feeadjuster-enough-liquidity"))
    plugin.imbalance = float(options.get("feeadjuster-imbalance"))
    adjustment_switch = {
        "soft": get_ratio_soft,
        "hard": get_ratio_hard,
        "default": get_ratio
    }
    plugin.get_ratio = adjustment_switch.get(options.get("feeadjuster-adjustment-method"), get_ratio)
    config = plugin.rpc.listconfigs()
    plugin.adj_basefee = config["fee-base"]
    plugin.adj_ppmfee = config["fee-per-satoshi"]

    # normalize the imbalance percentage value to 0%-50%
    if plugin.imbalance < 0 or plugin.imbalance > 1:
        raise ValueError("feeadjuster-imbalance must be between 0 and 1.")
    if plugin.imbalance > 0.5:
        plugin.imbalance = 1 - plugin.imbalance

    plugin.log(f"Plugin feeadjuster initialized ({plugin.adj_basefee} base / {plugin.adj_ppmfee} ppm) with an "
               f"imbalance of {int(100 * plugin.imbalance)}%/{int(100 * ( 1 - plugin.imbalance))}%, "
               f"update_threshold: {int(100 * plugin.update_threshold)}%, update_threshold_abs: {plugin.update_threshold_abs}, "
               f"enough_liquidity: {plugin.big_enough_liquidity}, deactivate_fuzz: {plugin.deactivate_fuzz}, "
               f"forward_event_subscription: {plugin.forward_event_subscription}, adjustment_method: {plugin.get_ratio.__name__}")
    plugin.mutex.release()
    feeadjust(plugin)


plugin.add_option(
    "feeadjuster-deactivate-fuzz",
    False,
    "Deactivate update threshold randomization and hysterisis.",
    "flag"
)
plugin.add_option(
    "feeadjuster-deactivate-fee-update",
    False,
    "Deactivate automatic fee updates for forward events.",
    "flag"
)
plugin.add_option(
    "feeadjuster-threshold",
    "0.05",
    "Relative channel balance delta at which to trigger an update. Default 0.05 means 5%. "
    "Note: it's also fuzzed by 1.5%",
    "string"
)
plugin.add_option(
    "feeadjuster-threshold-abs",
    "0.001btc",
    "Absolute channel balance delta at which to always trigger an update. "
    "Note: it's also fuzzed by 1.5%",
    "string"
)
plugin.add_option(
    "feeadjuster-enough-liquidity",
    "0msat",
    "Beyond this liquidity do not adjust fees. "
    "This also modifies the fee curve to achieve having this amount of liquidity. "
    "Default: '0msat' (turned off).",
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
