#!/usr/bin/env python3
import random
import statistics
import time
import math
from clnutils import cln_parse_rpcversion
from pyln.client import Plugin, Millisatoshi, RpcError
from threading import Lock


plugin = Plugin()
# Our amount and the total amount in each of our channel, indexed by scid
plugin.adj_balances = {}
# Cache to avoid loads of RPC calls
plugin.our_node_id = None
plugin.peerchannels = None
plugin.channels = None
plugin.excludelist = None
# Users can configure this
plugin.update_threshold = 0.05
# forward_event must wait for init
plugin.mutex = Lock()
plugin.mutex.acquire()


def read_excludelist():
    try:
        with open("feeadjuster-exclude.list") as file:
            exclude_list = [l.rstrip("\n") for l in file]
            print("Excluding the channels with the nodes:", exclude_list)
    except FileNotFoundError:
        exclude_list = []
        print(
            "There is no feeadjuster-exclude.list given, applying the options to the channels with all peers."
        )
    return exclude_list


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
    return 10 ** (0.5 - our_percentage)


def get_ratio(our_percentage):
    """
    Basic algorithm: the farther we are from the optimal case, the more we
    bump/lower.
    """
    return 50 ** (0.5 - our_percentage)


def get_ratio_hard(our_percentage):
    """
    Return value is between 0 and 20: 0 -> 20; 0.5 -> 1; 1 -> 0
    """
    return 100 ** (0.5 - our_percentage) * (1 - our_percentage) * 2


def get_peerchannels(plugin: Plugin):
    """Helper to reconstruct `listpeerchannels` for older CLN versions"""
    # first the good case
    if (
        plugin.rpcversion[0] > 23
        or plugin.rpcversion[0] == 23
        and plugin.rpcversion[1] >= 2
    ):
        return plugin.rpc.listpeerchannels()["channels"]
    # now the workaround
    channels = []
    peers = plugin.rpc.listpeers()["peers"]
    for peer in peers:
        newchans = peer["channels"]
        for ch in newchans:
            ch["peer_id"] = peer["id"]  # all we need is to set the 'peer_id'
        channels.extend(newchans)
    return channels


def get_config(plugin: Plugin, config: str):
    """Helper to reconstruct `listconfigs` for older CLN versions"""
    # versions >=23.08 return a configs object and value_* fields
    if (
        plugin.rpcversion[0] > 23
        or plugin.rpcversion[0] == 23
        and plugin.rpcversion[1] >= 8
    ):
        result = plugin.rpc.listconfigs(config)["configs"]
        assert len(result) > 0
        conf_obj = result[config]
        if "value_str" in conf_obj:
            return conf_obj["value_str"]
        elif "value_msat" in conf_obj:
            return conf_obj["value_msat"]
        elif "value_int" in conf_obj:
            return conf_obj["value_int"]
        elif "value_bool" in conf_obj:
            return conf_obj["value_bool"]
        else:
            return None

    # now < 23.08
    result = plugin.rpc.listconfigs(config)
    if len(result) == 0:
        return None
    return result[config]


def get_peer_id_for_scid(plugin: Plugin, scid: str):
    for ch in plugin.peerchannels:
        if ch.get("short_channel_id") == scid:
            return ch["peer_id"]
    return None


def get_peerchannel(plugin: Plugin, scid: str):
    for ch in plugin.peerchannels:
        if ch.get("short_channel_id") == scid:
            return ch
    return None


def get_chan_fees(plugin: Plugin, scid: str):
    channel = get_peerchannel(plugin, scid)
    assert channel is not None
    return {
        "base": channel["fee_base_msat"],
        "ppm": channel["fee_proportional_millionths"],
    }


def get_fees_global(plugin: Plugin, scid: str):
    return {"base": plugin.adj_basefee, "ppm": plugin.adj_ppmfee}


def get_fees_median(plugin: Plugin, scid: str):
    """Median fees from peers or peer.

    The assumption is that our node competes in fees to other peers of a peer.
    """
    peer_id = get_peer_id_for_scid(plugin, scid)
    assert peer_id is not None
    if plugin.listchannels_by_dst:
        plugin.channels = plugin.rpc.call("listchannels", {"destination": peer_id})[
            "channels"
        ]
    channels_to_peer = [
        ch
        for ch in plugin.channels
        if ch["destination"] == peer_id and ch["source"] != plugin.our_node_id
    ]
    if len(channels_to_peer) == 0:
        return None
    # fees > ~5000 (base and ppm) are currently about top 2% of network fee extremists
    fees_ppm = [
        ch["fee_per_millionth"]
        for ch in channels_to_peer
        if 0 < ch["fee_per_millionth"] < 5000
    ]
    fees_base = [
        ch["base_fee_millisatoshi"]
        for ch in channels_to_peer
        if 0 < ch["base_fee_millisatoshi"] < 5000
    ]

    # if lists are emtpy use default values, otherwise statistics.median will fail.
    if len(fees_ppm) == 0:
        fees_ppm = [int(plugin.adj_ppmfee / plugin.median_multiplier)]
    if len(fees_base) == 0:
        fees_base = [int(plugin.adj_basefee / plugin.median_multiplier)]
    return {
        "base": statistics.median(fees_base) * plugin.median_multiplier,
        "ppm": statistics.median(fees_ppm) * plugin.median_multiplier,
    }


def setchannelfee(
    plugin: Plugin,
    scid: str,
    base: int,
    ppm: int,
    min_htlc: int = None,
    max_htlc: int = None,
):
    fees = get_chan_fees(plugin, scid)
    if fees is None or base == fees["base"] and ppm == fees["ppm"]:
        return False
    try:
        plugin.rpc.setchannel(scid, base, ppm, min_htlc, max_htlc)
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
    if (
        abs(last_percentage - percentage) > update_threshold
        or abs(last_liquidity - channel["our"]) > update_threshold_abs
    ):
        return True
    return False


def maybe_adjust_fees(plugin: Plugin, scids: list):
    channels_adjusted = 0
    for scid in scids:
        if (
            scid in plugin.exclude_list
            or get_peer_id_for_scid(plugin, scid) in plugin.exclude_list
        ):
            continue
        our = plugin.adj_balances[scid]["our"]
        total = plugin.adj_balances[scid]["total"]
        percentage = our / total
        base = int(plugin.adj_basefee)
        ppm = int(plugin.adj_ppmfee)

        # select ideal values per channel
        fees = plugin.fee_strategy(plugin, scid)
        if fees is not None:
            ppm = int(fees["ppm"])
            if plugin.basefee:
                base = int(fees["base"])

        # reset to normal fees if imbalance is not high enough
        if percentage > plugin.imbalance and percentage < 1 - plugin.imbalance:
            if setchannelfee(plugin, scid, base, ppm):
                plugin.log(
                    f"Set default fees as imbalance is too low for {scid}:   ppm {ppm}   base {base}msat"
                )
                plugin.adj_balances[scid]["last_liquidity"] = our
                channels_adjusted += 1
            continue

        if not significant_update(plugin, scid):
            continue

        percentage = get_adjusted_percentage(plugin, scid)
        assert 0 <= percentage and percentage <= 1
        ratio = plugin.get_ratio(percentage)
        if plugin.max_htlc_steps >= 1:
            max_htlc = int(
                total
                * math.ceil(plugin.max_htlc_steps * percentage)
                / plugin.max_htlc_steps
            )
        else:
            max_htlc = None
        if setchannelfee(plugin, scid, base, int(ppm * ratio), None, max_htlc):
            plugin.log(
                f"Adjusted fees of {scid} with a ratio of {ratio}:   ppm {int(ppm * ratio)}   base {base}msat   max_htlc {max_htlc}"
            )
            plugin.adj_balances[scid]["last_liquidity"] = our
            channels_adjusted += 1
    plugin.log("maybe_adjust_fees done", "debug")
    return channels_adjusted


def get_new_balance(plugin: Plugin, scid: str):
    i = 0
    while i < 5:
        chan = get_peerchannel(plugin, scid)
        assert chan is not None
        if scid not in plugin.adj_balances:
            time.sleep(5)
            plugin.peerchannels = get_peerchannels(plugin)
            chan = get_peerchannel(plugin, scid)
            plugin.adj_balances[scid] = {
                "our": int(chan["to_us_msat"]),
                "total": int(chan["total_msat"]),
            }
            return
        elif (
            int(chan["to_us_msat"]) != plugin.adj_balances[scid]["our"]
            or int(chan["total_msat"]) != plugin.adj_balances[scid]["total"]
        ):
            plugin.adj_balances[scid]["our"] = int(chan["to_us_msat"])
            plugin.adj_balances[scid]["total"] = int(chan["total_msat"])
            return
        else:
            time.sleep(1)
            plugin.peerchannels = get_peerchannels(plugin)
            i += 1


@plugin.subscribe("forward_event")
def forward_event(plugin: Plugin, forward_event: dict, **kwargs):
    if not plugin.forward_event_subscription:
        return
    if forward_event["status"] == "settled":
        plugin.mutex.acquire(blocking=True)
        plugin.peerchannels = get_peerchannels(plugin)
        if plugin.fee_strategy == get_fees_median and not plugin.listchannels_by_dst:
            plugin.channels = plugin.rpc.listchannels()["channels"]
        in_scid = forward_event["in_channel"]
        out_scid = forward_event["out_channel"]
        get_new_balance(plugin, in_scid)
        get_new_balance(plugin, out_scid)

        try:
            # Pseudo-randomly add some hysterisis to the update
            if not plugin.deactivate_fuzz and random.randint(0, 9) == 9:
                time.sleep(random.randint(0, 5))
            maybe_adjust_fees(plugin, [in_scid, out_scid])
        except Exception as e:
            plugin.log("Adjusting fees: " + str(e), level="error")
        plugin.mutex.release()


@plugin.method("feeadjust")
def feeadjust(plugin: Plugin, scid: str = None):
    """Adjust fees for all channels (default) or just a given `scid`.

    This method is automatically called in plugin init, or can be called manually after a successful payment.
    Otherwise, the plugin keeps the fees up-to-date.

    To stop adjusting the channels for a set PeerIDs or SCIDs, place a file
    called `feeadjuster-exclude.list` in the lightningd data directory with a
    simple line-by-line list of PeerIDs (pubkeys) or SCIDs.
    """
    plugin.mutex.acquire(blocking=True)
    plugin.peerchannels = get_peerchannels(plugin)
    if plugin.fee_strategy == get_fees_median and not plugin.listchannels_by_dst:
        plugin.channels = plugin.rpc.listchannels()["channels"]
    channels_adjusted = 0
    plugin.exclude_list = read_excludelist()

    for chan in plugin.peerchannels:
        if scid in plugin.exclude_list or chan["peer_id"] in plugin.exclude_list:
            continue
        if chan["state"] == "CHANNELD_NORMAL":
            _scid = chan.get("short_channel_id")
            if scid is not None and scid != _scid:
                continue
            plugin.adj_balances[_scid] = {
                "our": int(chan["to_us_msat"]),
                "total": int(chan["total_msat"]),
            }
            channels_adjusted += maybe_adjust_fees(plugin, [_scid])
    msg = f"{channels_adjusted} channel(s) adjusted"
    plugin.log(msg)
    plugin.mutex.release()
    return msg


@plugin.method("feeadjuster-toggle")
def feeadjuster_toggle(plugin: Plugin, value: bool = None):
    """Activates/Deactivates automatic fee updates for forward events.

    The status will be set to value.
    """
    msg = {
        "forward_event_subscription": {"previous": plugin.forward_event_subscription}
    }
    if value is None:
        plugin.forward_event_subscription = not plugin.forward_event_subscription
    else:
        plugin.forward_event_subscription = bool(value)
    msg["forward_event_subscription"]["current"] = plugin.forward_event_subscription
    return msg


@plugin.init()
def init(options: dict, configuration: dict, plugin: Plugin, **kwargs):
    # do all the stuff that needs to be done just once ...
    plugin.getinfo = plugin.rpc.getinfo()
    plugin.rpcversion = cln_parse_rpcversion(plugin.getinfo.get("version"))
    plugin.our_node_id = plugin.getinfo["id"]
    plugin.deactivate_fuzz = options.get("feeadjuster-deactivate-fuzz")
    plugin.forward_event_subscription = not options.get(
        "feeadjuster-deactivate-fee-update"
    )
    plugin.update_threshold = float(options.get("feeadjuster-threshold"))
    plugin.update_threshold_abs = Millisatoshi(options.get("feeadjuster-threshold-abs"))
    plugin.big_enough_liquidity = Millisatoshi(
        options.get("feeadjuster-enough-liquidity")
    )
    plugin.imbalance = float(options.get("feeadjuster-imbalance"))
    plugin.max_htlc_steps = int(options.get("feeadjuster-max-htlc-steps"))
    plugin.basefee = bool(options.get("feeadjuster-basefee"))
    adjustment_switch = {
        "soft": get_ratio_soft,
        "hard": get_ratio_hard,
        "default": get_ratio,
    }
    plugin.get_ratio = adjustment_switch.get(
        options.get("feeadjuster-adjustment-method"), get_ratio
    )
    fee_strategy_switch = {"global": get_fees_global, "median": get_fees_median}
    plugin.fee_strategy = fee_strategy_switch.get(
        options.get("feeadjuster-feestrategy"), get_fees_global
    )
    plugin.median_multiplier = float(options.get("feeadjuster-median-multiplier"))
    plugin.adj_basefee = get_config(plugin, "fee-base")
    if plugin.adj_basefee is None:
        plugin.adj_basefee = 1000
    plugin.adj_ppmfee = get_config(plugin, "fee-per-satoshi")
    if plugin.adj_ppmfee is None:
        plugin.adj_ppmfee = 10

    # normalize the imbalance percentage value to 0%-50%
    if plugin.imbalance < 0 or plugin.imbalance > 1:
        raise ValueError("feeadjuster-imbalance must be between 0 and 1.")
    if plugin.imbalance > 0.5:
        plugin.imbalance = 1 - plugin.imbalance

    # detect if server supports the new listchannels by `destination` (#4614)
    plugin.listchannels_by_dst = False
    rpchelp = plugin.rpc.help().get("help")
    if (
        len(
            [
                c
                for c in rpchelp
                if c["command"].startswith("listchannels ")
                and "destination" in c["command"]
            ]
        )
        == 1
    ):
        plugin.listchannels_by_dst = True

    # Detect if server supports new 'setchannel' command over setchannelfee.
    # If not, make plugin.rpc.setchannel a 'symlink' to setchannelfee
    if len([c for c in rpchelp if c["command"].startswith("setchannel ")]) == 0:
        plugin.rpc.setchannel = plugin.rpc.setchannelfee

    plugin.log(
        f"Plugin feeadjuster initialized "
        f"({plugin.adj_basefee} base / {plugin.adj_ppmfee} ppm) with an "
        f"imbalance of {int(100 * plugin.imbalance)}%/{int(100 * ( 1 - plugin.imbalance))}%, "
        f"update_threshold: {int(100 * plugin.update_threshold)}%, "
        f"update_threshold_abs: {plugin.update_threshold_abs}, "
        f"enough_liquidity: {plugin.big_enough_liquidity}, "
        f"deactivate_fuzz: {plugin.deactivate_fuzz}, "
        f"forward_event_subscription: {plugin.forward_event_subscription}, "
        f"adjustment_method: {plugin.get_ratio.__name__}, "
        f"fee_strategy: {plugin.fee_strategy.__name__}, "
        f"listchannels_by_dst: {plugin.listchannels_by_dst},"
        f"max_htlc_steps: {plugin.max_htlc_steps},"
        f"basefee: {plugin.basefee}"
    )
    plugin.mutex.release()
    feeadjust(plugin)


plugin.add_option(
    "feeadjuster-deactivate-fuzz",
    False,
    "Deactivate update threshold randomization and hysterisis.",
    "flag",
)
plugin.add_option(
    "feeadjuster-deactivate-fee-update",
    False,
    "Deactivate automatic fee updates for forward events.",
    "flag",
)
plugin.add_option(
    "feeadjuster-threshold",
    "0.05",
    "Relative channel balance delta at which to trigger an update. Default 0.05 means 5%. "
    "Note: it's also fuzzed by 1.5%",
    "string",
)
plugin.add_option(
    "feeadjuster-threshold-abs",
    "0.001btc",
    "Absolute channel balance delta at which to always trigger an update. "
    "Note: it's also fuzzed by 1.5%",
    "string",
)
plugin.add_option(
    "feeadjuster-enough-liquidity",
    "0msat",
    "Beyond this liquidity do not adjust fees. "
    "This also modifies the fee curve to achieve having this amount of liquidity. "
    "Default: '0msat' (turned off).",
    "string",
)
plugin.add_option(
    "feeadjuster-adjustment-method",
    "default",
    "Adjustment method to calculate channel fee"
    "Can be 'default', 'soft' for less difference or 'hard' for higher difference"
    "string",
)
plugin.add_option(
    "feeadjuster-imbalance",
    "0.5",
    "Ratio at which channel imbalance the feeadjuster should start acting. "
    "Default: 0.5 (always). Set higher or lower values to limit feeadjuster's "
    "activity to more imbalanced channels. "
    "E.g. 0.3 for '70/30'% or 0.6 for '40/60'%.",
    "string",
)
plugin.add_option(
    "feeadjuster-feestrategy",
    "global",
    "Sets the per channel fee selection strategy. "
    "Can be 'global' to use global config or default values, "
    "or 'median' to use the median fees from peers of peer "
    "Default: 'global'.",
    "string",
)
plugin.add_option(
    "feeadjuster-median-multiplier",
    "1.0",
    "Sets the factor with which the median fee is multiplied if using the fee strategy 'median'. "
    "This allows over or underbidding other nodes by a constant factor"
    "Default: '1.0'.",
    "string",
)
plugin.add_option(
    "feeadjuster-max-htlc-steps",
    "0",
    "Sets the number of max htlc adjustment steps. "
    "This will reduce the max htlc according to available "
    "liquidity, which can reduce local routing channel failures."
    "A value of 0 disables the stepping.",
    "string",
)
plugin.add_option(
    "feeadjuster-basefee",
    False,
    "Also adjust base fee dynamically. Currently only affects median strategy.",
    "bool",
)
plugin.run()
