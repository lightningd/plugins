#!/usr/bin/env python3
from clnutils import cln_parse_rpcversion
from datetime import timedelta
from functools import reduce
from pyln.client import Plugin, Millisatoshi, RpcError
import threading
import time
import uuid
import concurrent.futures

plugin = Plugin()
plugin.rebalance_stop_by_user = False
plugin.rebalance_stop_by_thread = False
plugin.rebalance_stop_by_event = False
plugin.threadids = {}


def rebalance_stopping():
    return (
        plugin.rebalance_stop_by_user
        or plugin.rebalance_stop_by_thread
        or plugin.rebalance_stop_by_event
    )


def get_thread_id_str():
    max_digits = len(str(plugin.threads - 1))
    return f"{plugin.threadids.get(threading.get_ident(), 0):{'0' + str(max_digits)}}"


# The route msat helpers are needed because older versions of cln
# had different msat/msatoshi fields with different types Millisatoshi/int
def route_set_msat(obj, msat):
    if plugin.rpcversion[0] == 0 and plugin.rpcversion[1] < 12:
        obj[plugin.msatfield] = msat.millisatoshis
        obj["amount_msat"] = Millisatoshi(msat)
    else:
        obj[plugin.msatfield] = Millisatoshi(msat)


def route_get_msat(r):
    return Millisatoshi(r[plugin.msatfield])


def setup_routing_fees(route, msat):
    delay = plugin.cltv_final
    for r in reversed(route):
        route_set_msat(r, msat)
        r["delay"] = delay
        channels = plugin.rpc.listchannels(r["channel"])
        ch = next(c for c in channels.get("channels") if c["destination"] == r["id"])
        fee = Millisatoshi(ch["base_fee_millisatoshi"])
        # BOLT #7 requires fee >= fee_base_msat + ( amount_to_forward * fee_proportional_millionths / 1000000 )
        fee += (
            msat * ch["fee_per_millionth"] + 10**6 - 1
        ) // 10**6  # integer math trick to round up
        msat += fee
        delay += ch["delay"]


def get_channel(payload, peer_id, scid, check_state: bool = False):
    if plugin.listpeerchannels:
        channels = plugin.rpc.listpeerchannels(peer_id)["channels"]
        channel = next(c for c in channels if c.get("short_channel_id") == scid)
        if check_state:
            if channel["state"] != "CHANNELD_NORMAL":
                raise RpcError(
                    "rebalance",
                    payload,
                    {
                        "message": "Channel %s not in state CHANNELD_NORMAL, but: %s"
                        % (scid, channel["state"])
                    },
                )
            if not channel["peer_connected"]:
                raise RpcError(
                    "rebalance",
                    payload,
                    {"message": "Channel %s peer is not connected." % scid},
                )
        return channel
    peer = plugin.rpc.listpeers(peer_id).get("peers")[0]
    channel = next(c for c in peer["channels"] if c.get("short_channel_id") == scid)
    if check_state:
        if channel["state"] != "CHANNELD_NORMAL":
            raise RpcError(
                "rebalance",
                payload,
                {
                    "message": "Channel %s not in state CHANNELD_NORMAL, but: %s"
                    % (scid, channel["state"])
                },
            )
        if not peer["connected"]:
            raise RpcError(
                "rebalance",
                payload,
                {"message": "Channel %s peer is not connected." % scid},
            )
    return channel


def amounts_from_scid(scid):
    channels = plugin.rpc.listfunds().get("channels")
    channel = next(c for c in channels if c.get("short_channel_id") == scid)
    our_msat = Millisatoshi(channel["our_amount_msat"])
    total_msat = Millisatoshi(channel["amount_msat"])
    return our_msat, total_msat


def peer_from_scid(short_channel_id, my_node_id, payload):
    channels = plugin.rpc.listchannels(short_channel_id).get("channels")
    for ch in channels:
        if ch["source"] == my_node_id:
            return ch["destination"]
    raise RpcError(
        "rebalance",
        payload,
        {"message": "Cannot find peer for channel: " + short_channel_id},
    )


def get_node_alias(node_id):
    node = plugin.rpc.listnodes(node_id)["nodes"]
    s = ""
    if len(node) != 0 and "alias" in node[0]:
        s += node[0]["alias"]
    else:
        s += node_id[0:7]
    return s


def find_worst_channel(route):
    if len(route) < 4:
        return None
    start_idx = 2
    worst = route[start_idx]
    worst_val = route_get_msat(route[start_idx - 1]) - route_get_msat(worst)
    for i in range(start_idx + 1, len(route) - 1):
        val = route_get_msat(route[i - 1]) - route_get_msat(route[i])
        if val > worst_val:
            worst = route[i]
            worst_val = val
    return worst


def cleanup(label, payload, rpc_result, error=None):
    try:
        plugin.rpc.delinvoice(label, "unpaid")
    except RpcError as e:
        # race condition: waitsendpay timed out, but invoice get paid
        if "status is paid" in e.error.get("message", ""):
            return rpc_result

    if error is not None:
        if isinstance(error, RpcError):
            # unwrap rebalance errors as 'normal' RPC result
            if error.method == "rebalance":
                return {
                    "status": "exception",
                    "message": error.error.get("message", "error not given"),
                }
        raise error

    return rpc_result


# This function calculates the optimal rebalance amount
# based on the selected channels capacity and state.
# It will return a value that brings at least one of the channels to balance.
# It will raise an error, when this isnt possible.
#
# EXAMPLE
#             |------------------- out_total -------------|
# OUT   -v => |-------- out_ours -------||-- out_theirs --| => +v
#
# IN                +v <= |-- in_ours --||---------- in_theirs ---------| <= -v
#                         |--------- in_total --------------------------|
#
# CHEAP SOLUTION: take v_min from 50/50 values
# O*   vo = out_ours - (out_total/2)
# I*   vi = (in_total/2) - in_ours
# return min(vo, vi)
#
# ... and cover edge cases with exceeding in/out capacity or negative values.
def calc_optimal_amount(out_ours, out_total, in_ours, in_total, payload):
    out_ours, out_total = int(out_ours), int(out_total)
    in_ours, in_total = int(in_ours), int(in_total)

    in_theirs = in_total - in_ours
    vo = int(out_ours - (out_total / 2))
    vi = int((in_total / 2) - in_ours)

    # cases where one option can be eliminated because it exceeds other capacity
    if vo > in_theirs and vi > 0 and vi < out_ours:
        return Millisatoshi(vi)
    if vi > out_ours and vo > 0 and vo < in_theirs:
        return Millisatoshi(vo)

    # cases where one channel is still capable to bring other to balance
    if vo < 0 and vi > 0 and vi < out_ours:
        return Millisatoshi(vi)
    if vi < 0 and vo > 0 and vo < in_theirs:
        return Millisatoshi(vo)

    # when both options are possible take the one with least effort
    if vo > 0 and vo < in_theirs and vi > 0 and vi < out_ours:
        return Millisatoshi(min(vi, vo))

    raise RpcError(
        "rebalance",
        payload,
        {"message": "rebalancing these channels will make things worse"},
    )


class NoRouteException(Exception):
    pass


def getroute_basic(targetid, fromid, excludes, amount_msat: Millisatoshi):
    try:
        """ This does not make special assumptions and tries all routes
            it gets. Uses less CPU and does not filter any routes.
        """
        return plugin.rpc.getroute(
            targetid,
            fromid=fromid,
            exclude=excludes,
            amount_msat=amount_msat,
            maxhops=plugin.maxhops,
            riskfactor=10,
            cltv=9,
        )
    except RpcError as e:
        # could not find route -> change params and restart loop
        if e.method == "getroute" and e.error.get("code") == 205:
            raise NoRouteException
        raise e


def getroute_iterative(targetid, fromid, excludes, amount_msat: Millisatoshi):
    """This searches for 'shorter and bigger pipes' first in order
    to increase likelyhood of success on short timeout.
    Can be useful for manual `rebalance`.
    """
    try:
        return plugin.rpc.getroute(
            targetid,
            fromid=fromid,
            exclude=excludes,
            amount_msat=amount_msat * plugin.msatfactoridx,
            maxhops=plugin.maxhopidx,
            riskfactor=10,
            cltv=9,
        )
    except RpcError as e:
        # could not find route -> change params and restart loop
        if e.method == "getroute" and e.error.get("code") == 205:
            # reduce _msatfactor to look for smaller channels now
            plugin.msatfactoridx -= 1
            if plugin.msatfactoridx < 1:
                # when we reached neutral msat factor:
                # increase _maxhops and restart with msatfactor
                plugin.maxhopidx += 1
                plugin.msatfactoridx = plugin.msatfactor
            # abort if we reached maxhop limit
            if plugin.maxhops > 0 and plugin.maxhopidx > plugin.maxhops:
                raise NoRouteException
        raise e


def getroute_switch(method_name):
    switch = {"basic": getroute_basic, "iterative": getroute_iterative}
    return switch.get(method_name, getroute_iterative)


def waitsendpay(payment_hash, start_ts, retry_for):
    while True:
        try:
            timeout = min(max(retry_for + start_ts - int(time.time()), 0), 10)
            result = plugin.rpc.waitsendpay(payment_hash, timeout)
            return result
        except RpcError as e:
            if e.method == "waitsendpay" and e.error.get("code") == 200:
                if rebalance_stopping():
                    raise e
                if int(time.time()) - start_ts >= retry_for:
                    raise e
            else:
                raise e


@plugin.method("rebalance")
def rebalance(
    plugin,
    outgoing_scid,
    incoming_scid,
    msatoshi: Millisatoshi = None,
    retry_for: int = 60,
    maxfeepercent: float = 0.5,
    exemptfee: Millisatoshi = Millisatoshi(5000),
    getroute_method=None,
):
    """Rebalancing channel liquidity with circular payments.

    This tool helps to move some msatoshis between your channels.
    """
    if msatoshi:
        msatoshi = Millisatoshi(msatoshi)
    retry_for = int(retry_for)
    maxfeepercent = float(maxfeepercent)
    if getroute_method is None:
        getroute = plugin.getroute
    else:
        getroute = getroute_switch(getroute_method)
    exemptfee = Millisatoshi(exemptfee)
    payload = {
        "outgoing_scid": outgoing_scid,
        "incoming_scid": incoming_scid,
        "msatoshi": msatoshi,
        "retry_for": retry_for,
        "maxfeepercent": maxfeepercent,
        "exemptfee": exemptfee,
    }
    my_node_id = plugin.getinfo.get("id")
    outgoing_node_id = peer_from_scid(outgoing_scid, my_node_id, payload)
    incoming_node_id = peer_from_scid(incoming_scid, my_node_id, payload)
    get_channel(payload, outgoing_node_id, outgoing_scid, True)
    get_channel(payload, incoming_node_id, incoming_scid, True)
    out_ours, out_total = amounts_from_scid(outgoing_scid)
    in_ours, in_total = amounts_from_scid(incoming_scid)

    # If amount was not given, calculate a suitable 50/50 rebalance amount
    if msatoshi is None:
        msatoshi = calc_optimal_amount(out_ours, out_total, in_ours, in_total, payload)
        plugin.log("Estimating optimal amount %s" % msatoshi)

    # Check requested amounts are selected channels
    if msatoshi > out_ours or msatoshi > in_total - in_ours:
        raise RpcError("rebalance", payload, {"message": "Channel capacities too low"})

    plugin.log(
        f"starting rebalance out_scid:{outgoing_scid} in_scid:{incoming_scid} amount:{msatoshi}",
        "debug",
    )

    route_out = {
        "id": outgoing_node_id,
        "channel": outgoing_scid,
        "direction": int(not my_node_id < outgoing_node_id),
    }
    route_in = {
        "id": my_node_id,
        "channel": incoming_scid,
        "direction": int(not incoming_node_id < my_node_id),
    }
    start_ts = int(time.time())
    label = "Rebalance-" + str(uuid.uuid4())
    description = "%s to %s" % (outgoing_scid, incoming_scid)
    invoice = plugin.rpc.invoice(msatoshi, label, description, retry_for + 60)
    payment_hash = invoice["payment_hash"]
    # The requirement for payment_secret coincided with its addition to the invoice output.
    payment_secret = invoice.get("payment_secret")

    rpc_result = None
    excludes = [my_node_id]  # excude all own channels to prevent shortcuts
    nodes = {}  # here we store erring node counts
    plugin.maxhopidx = 1  # start with short routes and increase
    plugin.msatfactoridx = plugin.msatfactor  # start with high capacity factor
    # and decrease to reduce WIRE_TEMPORARY failures because of imbalances

    # 'disable' maxhops filter if set to <= 0
    # I know this is ugly, but we don't ruin the rest of the code this way
    if plugin.maxhops <= 0:
        plugin.maxhopidx = 20

    # trace stats
    count = 0
    count_sendpay = 0
    time_getroute = 0
    time_sendpay = 0

    try:
        while int(time.time()) - start_ts < retry_for and not rebalance_stopping():
            count += 1
            try:
                time_start = time.time()
                r = getroute(
                    targetid=incoming_node_id,
                    fromid=outgoing_node_id,
                    excludes=excludes,
                    amount_msat=msatoshi,
                )
                time_getroute += time.time() - time_start
            except NoRouteException:
                # no more chance for a successful getroute
                rpc_result = {"status": "error", "message": "No suitable routes found"}
                return cleanup(label, payload, rpc_result)
            except RpcError as e:
                # getroute can be successful next time with different parameters
                if e.method == "getroute" and e.error.get("code") == 205:
                    continue
                else:
                    raise e

            route_mid = r["route"]
            route = [route_out] + route_mid + [route_in]
            setup_routing_fees(route, msatoshi)
            fees = route_get_msat(route[0]) - msatoshi

            # check fee and exclude worst channel the next time
            # NOTE: the int(msat) casts are just a workaround for outdated pylightning versions
            if fees > exemptfee and int(fees) > int(msatoshi) * maxfeepercent / 100:
                worst_channel = find_worst_channel(route)
                if worst_channel is None:
                    raise RpcError(
                        "rebalance", payload, {"message": "Insufficient fee"}
                    )
                excludes.append(
                    worst_channel["channel"] + "/" + str(worst_channel["direction"])
                )
                continue

            rpc_result = {
                "sent": msatoshi + fees,
                "received": msatoshi,
                "fee": fees,
                "hops": len(route),
                "outgoing_scid": outgoing_scid,
                "incoming_scid": incoming_scid,
                "status": "complete",
                "message": f"{msatoshi + fees} sent over {len(route)} hops to rebalance {msatoshi}",
            }
            midroute_str = reduce(
                lambda x, y: x + " -> " + y,
                map(lambda r: get_node_alias(r["id"]), route_mid),
            )
            full_route_str = "%s -> %s -> %s -> %s" % (
                get_node_alias(my_node_id),
                get_node_alias(outgoing_node_id),
                midroute_str,
                get_node_alias(my_node_id),
            )
            plugin.log(
                f"Thread{get_thread_id_str()} {len(route)} hops and {fees.to_satoshi_str()} fees for {msatoshi.to_satoshi_str()} along route: {full_route_str}"
            )
            for r in route:
                plugin.log(
                    "    - %s  %14s  %s" % (r["id"], r["channel"], route_get_msat(r)),
                    "debug",
                )

            time_start = time.time()
            count_sendpay += 1
            try:
                plugin.rpc.sendpay(route, payment_hash, payment_secret=payment_secret)
                result = waitsendpay(payment_hash, start_ts, retry_for)
                time_sendpay += time.time() - time_start
                if result.get("status") == "complete":
                    rpc_result["stats"] = (
                        f"running_for:{int(time.time()) - start_ts}  count_getroute:{count}  time_getroute:{time_getroute}  time_getroute_avg:{time_getroute / count}  count_sendpay:{count_sendpay}  time_sendpay:{time_sendpay}  time_sendpay_avg:{time_sendpay / count_sendpay}"
                    )
                    return cleanup(label, payload, rpc_result)

            except RpcError as e:
                time_sendpay += time.time() - time_start
                plugin.log(
                    f"maxhops:{plugin.maxhopidx}  msatfactor:{plugin.msatfactoridx}  running_for:{int(time.time()) - start_ts}  count_getroute:{count}  time_getroute:{time_getroute}  time_getroute_avg:{time_getroute / count}  count_sendpay:{count_sendpay}  time_sendpay:{time_sendpay}  time_sendpay_avg:{time_sendpay / count_sendpay}",
                    "debug",
                )
                # plugin.log(f"RpcError: {str(e)}", 'debug')
                # check if we ran into the `rpc.waitsendpay` timeout
                if e.method == "waitsendpay" and e.error.get("code") == 200:
                    raise RpcError("rebalance", payload, {"message": "Timeout reached"})
                # check if we have problems with our own channels
                erring_node = e.error.get("data", {}).get("erring_node")
                erring_channel = e.error.get("data", {}).get("erring_channel")
                erring_direction = e.error.get("data", {}).get("erring_direction")
                if erring_channel == incoming_scid:
                    raise RpcError(
                        "rebalance", payload, {"message": "Error with incoming channel"}
                    )
                if erring_channel == outgoing_scid:
                    raise RpcError(
                        "rebalance", payload, {"message": "Error with outgoing channel"}
                    )
                # exclude other erroring channels
                if erring_channel is not None and erring_direction is not None:
                    excludes.append(erring_channel + "/" + str(erring_direction))
                # count and exclude nodes that produce a lot of errors
                if erring_node and plugin.erringnodes > 0:
                    if nodes.get(erring_node) is None:
                        nodes[erring_node] = 0
                    nodes[erring_node] += 1
                    if nodes[erring_node] >= plugin.erringnodes:
                        excludes.append(erring_node)

    except Exception as e:
        return cleanup(label, payload, rpc_result, e)
    rpc_result = {"status": "error", "message": "Timeout reached"}
    return cleanup(label, payload, rpc_result)


def a_minus_b(a: Millisatoshi, b: Millisatoshi):
    # a minus b, but Millisatoshi cannot be negative
    return a - b if a > b else Millisatoshi(0)


def must_send(liquidity):
    # liquidity is too high, must send some sats
    return a_minus_b(liquidity["min"], liquidity["their"])


def should_send(liquidity):
    # liquidity is a bit high, would be good to send some sats
    return a_minus_b(liquidity["ideal"]["their"], liquidity["their"])


def could_send(liquidity):
    # liquidity maybe a bit low, but can send some more sats, if needed
    return a_minus_b(liquidity["our"], liquidity["min"])


def must_receive(liquidity):
    # liquidity is too low, must receive some sats
    return a_minus_b(liquidity["min"], liquidity["our"])


def should_receive(liquidity):
    # liquidity is a bit low, would be good to receive some sats
    return a_minus_b(liquidity["ideal"]["our"], liquidity["our"])


def could_receive(liquidity):
    # liquidity maybe a bit high, but can receive some more sats, if needed
    return a_minus_b(liquidity["their"], liquidity["min"])


def get_open_channels(plugin: Plugin):
    result = []
    if plugin.listpeerchannels:
        channels = plugin.rpc.listpeerchannels()["channels"]
        for ch in channels:
            if ch["state"] == "CHANNELD_NORMAL" and not ch["private"]:
                result.append(ch)
    else:
        for peer in plugin.rpc.listpeers()["peers"]:
            for ch in peer["channels"]:
                if ch["state"] == "CHANNELD_NORMAL" and not ch["private"]:
                    result.append(ch)
    return result


def check_liquidity_threshold(channels: list, threshold: Millisatoshi):
    # check if overall rebalances can be successful with this threshold
    our = sum(ch["to_us_msat"] for ch in channels)
    total = sum(ch["total_msat"] for ch in channels)
    required = Millisatoshi(0)
    for ch in channels:
        required += min(threshold, Millisatoshi(ch["total_msat"]) / 2)
    return required < our and required < total - our


def get_enough_liquidity_threshold(channels: list):
    low = Millisatoshi(0)
    biggest_channel = max(channels, key=lambda ch: ch["total_msat"])
    high = Millisatoshi(biggest_channel["total_msat"]) / 2
    while True:
        mid = (low + high) / 2
        if high - low < Millisatoshi("1sat"):
            break
        if check_liquidity_threshold(channels, mid):
            low = mid
        else:
            high = mid
    return mid / 2


def get_ideal_ratio(channels: list, enough_liquidity: Millisatoshi):
    # ideal liquidity ratio for big channels:
    # small channels should have a 50/50 liquidity ratio to be usable
    # and big channels can store the remaining liquidity above the threshold
    assert len(channels) > 0
    our = sum(Millisatoshi(ch["to_us_msat"]) for ch in channels)
    total = sum(Millisatoshi(ch["total_msat"]) for ch in channels)
    chs = list(channels)  # get a copy!
    while len(chs) > 0:
        ratio = int(our) / int(total)
        smallest_channel = min(chs, key=lambda ch: ch["total_msat"])
        if (
            Millisatoshi(smallest_channel["total_msat"]) * min(ratio, 1 - ratio)
            > enough_liquidity
        ):
            break
        min_liquidity = min(
            Millisatoshi(smallest_channel["total_msat"]) / 2, enough_liquidity
        )
        diff = Millisatoshi(smallest_channel["total_msat"]) * ratio
        diff = max(diff, min_liquidity)
        diff = min(diff, Millisatoshi(smallest_channel["total_msat"]) - min_liquidity)
        our -= diff
        total -= Millisatoshi(smallest_channel["total_msat"])
        chs.remove(smallest_channel)
    assert 0 <= ratio and ratio <= 1
    return ratio


def feeadjust_would_be_nice():
    commands = [
        c
        for c in plugin.rpc.help().get("help")
        if c["command"].split()[0] == "feeadjust"
    ]
    if len(commands) == 1:
        msg = plugin.rpc.feeadjust()
        plugin.log(f"Feeadjust succeeded: {msg}")
    else:
        plugin.log("The feeadjuster plugin would be useful here")


def get_max_amount(i: int, plugin: Plugin):
    return max(plugin.min_amount, plugin.enough_liquidity / (4**i))


def get_max_fee(msat: Millisatoshi):
    # TODO: sanity check
    return (plugin.fee_base + msat * plugin.fee_ppm / 10**6) * plugin.feeratio


def get_chan(scid: str):
    if plugin.listpeerchannels:
        channels = plugin.rpc.listpeerchannels()["channels"]
        for chan in channels:
            if chan.get("short_channel_id") == scid:
                return chan
    else:
        for peer in plugin.rpc.listpeers()["peers"]:
            if len(peer["channels"]) == 0:
                continue
            for chan in peer["channels"]:
                if chan.get("short_channel_id") == scid:
                    return chan


def liquidity_info(channel, enough_liquidity: Millisatoshi, ideal_ratio: float):
    liquidity = {
        "our": Millisatoshi(channel["to_us_msat"]),
        "their": Millisatoshi(channel["total_msat"] - channel["to_us_msat"]),
        "min": min(enough_liquidity, Millisatoshi(channel["total_msat"]) / 2),
        "max": max(
            a_minus_b(Millisatoshi(channel["total_msat"]), enough_liquidity),
            Millisatoshi(channel["total_msat"]) / 2,
        ),
        "ideal": {},
    }
    liquidity["ideal"]["our"] = min(
        max(Millisatoshi(channel["total_msat"]) * ideal_ratio, liquidity["min"]),
        liquidity["max"],
    )
    liquidity["ideal"]["their"] = min(
        max(Millisatoshi(channel["total_msat"]) * (1 - ideal_ratio), liquidity["min"]),
        liquidity["max"],
    )
    return liquidity


def wait_for(success, timeout: int = 60):
    # cyclical lambda helper
    # taken and modified from pyln-testing/pyln/testing/utils.py
    start_time = time.time()
    interval = 0.25
    while not success():
        time_left = start_time + timeout - time.time()
        if time_left <= 0:
            return False
        time.sleep(min(interval, time_left))
        interval *= 2
        if interval > 5:
            interval = 5
    return True


def wait_for_htlcs(failed_channels: list, scids: list = None):
    # HTLC settlement helper
    # taken and modified from pyln-testing/pyln/testing/utils.py
    result = True
    peers = plugin.rpc.listpeers()["peers"]
    for p, peer in enumerate(peers):
        pid = peer["id"]
        channels = []
        if "channels" in peer:
            channels = peer["channels"]
        elif "num_channels" in peer and peer["num_channels"] > 0:
            channels = plugin.rpc.listpeerchannels(peer["id"])["channels"]
        for c, channel in enumerate(channels):
            scid = channel.get("short_channel_id")
            if scids is not None and scid not in scids:
                continue
            if scid in failed_channels:
                result = False
                continue
            if "htlcs" in channel:
                lam = (
                    lambda: len(
                        plugin.rpc.listpeers()["peers"][p]["channels"][c]["htlcs"]
                    )
                    == 0
                )
                if plugin.listpeerchannels:
                    lam = (
                        lambda: len(
                            plugin.rpc.listpeerchannels(pid)["channels"][c]["htlcs"]
                        )
                        == 0
                    )
                if not wait_for(lam):
                    failed_channels.append(scid)
                    plugin.log(
                        f"Thread{get_thread_id_str()} timeout while waiting for htlc settlement in channel {scid}"
                    )
                    result = False
    return result


def maybe_rebalance_pairs(ch1, ch2, failed_channels: list):
    scid1 = ch1["short_channel_id"]
    scid2 = ch2["short_channel_id"]
    result = {"success": False, "fee_spent": Millisatoshi(0)}
    if scid1 + ":" + scid2 in failed_channels:
        return result
    # check if HTLCs are settled
    if not wait_for_htlcs(failed_channels, [scid1, scid2]):
        return result
    i = 0
    while not rebalance_stopping():
        liquidity1 = liquidity_info(ch1, plugin.enough_liquidity, plugin.ideal_ratio)
        liquidity2 = liquidity_info(ch2, plugin.enough_liquidity, plugin.ideal_ratio)
        amount1 = min(must_send(liquidity1), could_receive(liquidity2))
        amount2 = min(should_send(liquidity1), should_receive(liquidity2))
        amount3 = min(could_send(liquidity1), must_receive(liquidity2))
        amount = max(amount1, amount2, amount3)
        if amount < plugin.min_amount:
            return result
        amount = min(amount, get_max_amount(i, plugin))
        maxfee = get_max_fee(amount)
        plugin.log(
            f"Thread{get_thread_id_str()} tries to rebalance: {scid1} -> {scid2}; amount={amount.to_satoshi_str()}; maxfee={maxfee.to_satoshi_str()}"
        )
        start_ts = time.time()
        try:
            res = rebalance(
                plugin,
                outgoing_scid=scid1,
                incoming_scid=scid2,
                msatoshi=amount,
                retry_for=1200,
                maxfeepercent=0,
                exemptfee=maxfee,
            )
            if not res.get("status") == "complete":
                raise Exception  # fall into exception handler below
        except Exception:
            failed_channels.append(scid1 + ":" + scid2)
            # rebalance failed, let's try with a smaller amount
            while get_max_amount(i, plugin) >= amount and get_max_amount(
                i, plugin
            ) != get_max_amount(i + 1, plugin):
                i += 1
            if amount > get_max_amount(i, plugin):
                continue
            return result
        result["success"] = True
        result["fee_spent"] += res["fee"]
        htlc_start_ts = time.time()
        # wait for settlement
        htlc_success = wait_for_htlcs(failed_channels, [scid1, scid2])
        current_ts = time.time()
        res["elapsed_time"] = str(timedelta(seconds=current_ts - start_ts))[:-3]
        res["htlc_time"] = str(timedelta(seconds=current_ts - htlc_start_ts))[:-3]
        plugin.log(f"Thread{get_thread_id_str()} rebalance succeeded: {res}")
        if not htlc_success:
            return result
        ch1 = get_chan(scid1)
        assert ch1 is not None
        ch2 = get_chan(scid2)
        assert ch2 is not None
    return result


def rebalance_pair_picker(threadid, channel_pairs: list, failed_channels: list):
    plugin.threadids[threading.get_ident()] = threadid
    result = {"success": False, "fee_spent": Millisatoshi(0)}
    idle_count = 0
    while not rebalance_stopping():
        idle_count += 1
        for pair in channel_pairs:
            if rebalance_stopping():
                return result
            ch1 = pair[0]
            ch2 = pair[1]
            processed = pair[2]
            if processed:
                continue
            if ch1["lock"].acquire(blocking=False):
                if ch2["lock"].acquire(blocking=False):
                    idle_count = 0
                    pair[2] = True
                    result = maybe_rebalance_pairs(ch1, ch2, failed_channels)
                    ch2["lock"].release()
                ch1["lock"].release()
            if result["success"]:
                plugin.log(
                    f"Thread{get_thread_id_str()} restarts rebalance threads after successful rebalance"
                )
                plugin.rebalance_stop_by_thread = True
                return result
        unprocessed = [p for p in channel_pairs if not p[2]]
        if len(unprocessed) == 0:
            return result
        if idle_count == 1:
            plugin.log(
                f"Thread{get_thread_id_str()} is idle, {len(unprocessed)} possible channel pairs remained"
            )
        if idle_count > 0:
            time.sleep(10)
    return result


def maybe_rebalance_once(failed_channels: list):
    channels = get_open_channels(plugin)
    for ch in channels:
        ch["lock"] = threading.Lock()
    channel_pairs = []
    for ch1 in channels:
        for ch2 in channels:
            if ch1 == ch2:
                continue
            channel_pairs.append([ch1, ch2, False])

    plugin.log(f"Start to rebalance {len(channel_pairs)} possible channel pairs")
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=plugin.threads)
    futures = set()
    for threadid in range(plugin.threads):
        futures.add(
            executor.submit(
                rebalance_pair_picker, threadid, channel_pairs, failed_channels
            )
        )
    result = {"success": False, "fee_spent": Millisatoshi(0)}
    for future in concurrent.futures.as_completed(futures):
        r2 = future.result()
        if r2["success"]:
            if result["success"]:
                result["fee_spent"] += r2["fee_spent"]
                result["success_count"] = result.get("success_count", 1) + 1
            else:
                result = r2
    plugin.rebalance_stop_by_thread = False
    return result


def feeadjuster_toggle(new_value: bool):
    commands = [
        c
        for c in plugin.rpc.help().get("help")
        if c["command"].split()[0] == "feeadjuster-toggle"
    ]
    if len(commands) == 1:
        msg = plugin.rpc.feeadjuster_toggle(new_value)
        return msg["forward_event_subscription"]["previous"]
    else:
        return True


def refresh_parameters():
    channels = get_open_channels(plugin)
    plugin.enough_liquidity = get_enough_liquidity_threshold(channels)
    plugin.ideal_ratio = get_ideal_ratio(channels, plugin.enough_liquidity)
    plugin.log(
        f"Automatic rebalance is running with enough liquidity threshold: {plugin.enough_liquidity.to_satoshi_str()}, "
        f"ideal liquidity ratio: {plugin.ideal_ratio * 100:.2f}%, "
        f"min rebalancable amount: {plugin.min_amount.to_satoshi_str()}, "
        f"feeratio: {plugin.feeratio}"
    )


def rebalanceall_thread():
    if not plugin.mutex.acquire(blocking=False):
        return
    try:
        start_ts = time.time()
        feeadjuster_state = feeadjuster_toggle(False)
        plugin.log("Automatic rebalance started")
        failed_channels = []
        success = 0
        fee_spent = Millisatoshi(0)
        while True:
            refresh_parameters()
            result = maybe_rebalance_once(failed_channels)
            if not result["success"] and not plugin.rebalance_stop_by_event:
                break
            if result["success"]:
                success += result.get("success_count", 1)
                fee_spent += result["fee_spent"]
            plugin.rebalance_stop_by_event = False
            if rebalance_stopping():
                break
        feeadjust_would_be_nice()
        feeadjuster_toggle(feeadjuster_state)
        elapsed_time = timedelta(seconds=time.time() - start_ts)
        plugin.rebalanceall_msg = (
            f"Automatic rebalance finished: {success} successful rebalance, "
            f"{fee_spent.to_satoshi_str()} fee spent, it took {str(elapsed_time)[:-3]}"
        )
        plugin.log(plugin.rebalanceall_msg)
    finally:
        plugin.mutex.release()


@plugin.subscribe("forward_event")
def forward_event(plugin: Plugin, forward_event: dict, **kwargs):
    if not plugin.mutex.locked():
        return
    if forward_event["status"] == "settled":
        plugin.log("Forward event restarts rebalance threads")
        plugin.rebalance_stop_by_event = True


@plugin.subscribe("invoice_payment")
def invoice_payment(plugin: Plugin, invoice_payment: dict, **kwargs):
    if not plugin.mutex.locked():
        return
    if invoice_payment.get("label").startswith("Rebalance"):
        return
    plugin.log("Invoice payment restarts rebalance threads")
    plugin.rebalance_stop_by_event = True


@plugin.subscribe("sendpay_success")
def sendpay_success(plugin: Plugin, sendpay_success: dict, **kwargs):
    if not plugin.mutex.locked():
        return
    my_node_id = plugin.getinfo.get("id")
    if sendpay_success.get("destination") == my_node_id:
        return
    plugin.log("Sendpay success restarts rebalance threads")
    plugin.rebalance_stop_by_event = True


@plugin.subscribe("channel_state_changed")
def channel_state_changed(plugin: Plugin, channel_state_changed: dict, **kwargs):
    if not plugin.mutex.locked():
        return
    if (
        channel_state_changed.get("old_state") != "CHANNELD_NORMAL"
        and channel_state_changed.get("new_state") != "CHANNELD_NORMAL"
    ):
        return
    plugin.log("Channel state changed restarts rebalance threads")
    plugin.rebalance_stop_by_event = True


@plugin.method("rebalanceall")
def rebalanceall(
    plugin: Plugin,
    min_amount: Millisatoshi = Millisatoshi("50000sat"),
    feeratio: float = 0.5,
):
    """Rebalance all unbalanced channels if possible for a very low fee.
    Default minimum rebalancable amount is 50000sat. Default feeratio = 0.5, half of our node's default fee.
    To be economical, it tries to fix the liquidity cheaper than it can be ruined by transaction forwards.
    It may run for a long time (hours) in the background, but can be stopped with the rebalancestop method.
    """
    # some early checks before we start the async thread
    if plugin.mutex.locked():
        return {
            "message": "Rebalance is already running, this may take a while. To stop it use the cli method 'rebalancestop'."
        }
    channels = get_open_channels(plugin)
    if len(channels) <= 1:
        return {"message": "Error: Not enough open channels to rebalance anything"}
    our = sum(ch["to_us_msat"] for ch in channels)
    total = sum(ch["total_msat"] for ch in channels)
    min_amount = Millisatoshi(min_amount)
    if total - our < min_amount or our < min_amount:
        return {"message": "Error: Not enough liquidity to rebalance anything"}

    # param parsing ensure correct type
    plugin.feeratio = float(feeratio)
    plugin.min_amount = min_amount

    # run the job
    t = threading.Thread(target=rebalanceall_thread, args=())
    t.start()
    return {
        "message": f"Rebalance started with min rebalancable amount: {plugin.min_amount}, feeratio: {plugin.feeratio}"
    }


@plugin.method("rebalancestop")
def rebalancestop(plugin: Plugin):
    """It stops the ongoing rebalanceall."""
    if not plugin.mutex.locked():
        if plugin.rebalanceall_msg is None:
            return {"message": "No rebalance is running, nothing to stop."}
        return {
            "message": f"No rebalance is running, nothing to stop. "
            f"Last 'rebalanceall' gave: {plugin.rebalanceall_msg}"
        }
    start_ts = time.time()
    plugin.rebalance_stop_by_user = True
    plugin.mutex.acquire(blocking=True)
    plugin.rebalance_stop_by_user = False
    plugin.mutex.release()
    elapsed_time = timedelta(seconds=time.time() - start_ts)
    plugin.log(f"Automatic rebalance stopped in {str(elapsed_time)[:-3]}")
    return {"message": plugin.rebalanceall_msg}


def health_score(liquidity):
    if (
        int(liquidity["ideal"]["our"]) == 0
        or int(liquidity["ideal"]["their"]) == 0
        or int(liquidity["min"]) == 0
    ):
        return 0
    score_our = int(liquidity["our"]) / int(liquidity["ideal"]["our"])
    score_their = int(liquidity["their"]) / int(liquidity["ideal"]["their"])
    # distance from ideal liquidity (between 50 and 100)
    score = min(score_our, score_their) * 50 + 50
    coefficient_our = int(liquidity["our"]) / int(liquidity["min"])
    coefficient_their = int(liquidity["their"]) / int(liquidity["min"])
    # distance from minimal liquidity as a coefficient (between 0 and 1)
    coefficient = min(coefficient_our, coefficient_their, 1)
    return score * coefficient


def get_avg_forward_fees(intervals):
    now = time.time()
    max_interval = max(intervals)
    total = [0] * len(intervals)
    fees = [0] * len(intervals)
    res = [0] * len(intervals)
    all_forwards = list(
        filter(
            lambda fwd: fwd.get("status") == "settled"
            and fwd.get("resolved_time", 0) + max_interval * 60 * 60 * 24 > now,
            plugin.rpc.listforwards()["forwards"],
        )
    )

    # build intermediate result per interval
    for fwd in all_forwards:
        for idx, i in enumerate(intervals):
            if now > fwd["resolved_time"] + i * 60 * 60 * 24:
                continue
            total[idx] += fwd["out_msat"]
            fees[idx] += fwd["fee_msat"]

    # return average intermediate
    for idx, i in enumerate(res):
        if int(total[idx]) > 0:
            res[idx] = fees[idx] / total[idx] * 10**6
        else:
            res[idx] = 0
    return res


@plugin.method("rebalancereport")
def rebalancereport(plugin: Plugin, include_avg_fees: bool = True):
    """Show information about rebalance"""
    res = {}
    res["rebalanceall_is_running"] = plugin.mutex.locked()
    res["getroute_method"] = plugin.getroute.__name__
    res["maxhops_threshold"] = plugin.maxhops
    res["msatfactor"] = plugin.msatfactor
    res["erringnodes_threshold"] = plugin.erringnodes
    channels = get_open_channels(plugin)
    health_percent = 0.0
    if len(channels) > 1:
        enough_liquidity = get_enough_liquidity_threshold(channels)
        ideal_ratio = get_ideal_ratio(channels, enough_liquidity)
        res["enough_liquidity_threshold"] = enough_liquidity
        res["ideal_liquidity_ratio"] = f"{ideal_ratio * 100:.2f}%"
        for ch in channels:
            liquidity = liquidity_info(ch, enough_liquidity, ideal_ratio)
            health_percent += health_score(liquidity) * int(ch["total_msat"])
        health_percent /= int(sum(ch["total_msat"] for ch in channels))
    else:
        res["enough_liquidity_threshold"] = Millisatoshi(0)
        res["ideal_liquidity_ratio"] = "0%"
    res["liquidity_health"] = f"{health_percent:.2f}%"
    invoices = plugin.rpc.listinvoices()["invoices"]
    rebalances = [
        i
        for i in invoices
        if i.get("status") == "paid" and i.get("label").startswith("Rebalance")
    ]
    total_fee = Millisatoshi(0)
    total_amount = Millisatoshi(0)
    res["total_successful_rebalances"] = len(rebalances)

    # iterate if cln doesn't already support `status` on listpays since v0.10.2
    if (
        plugin.rpcversion[0] == 0
        and plugin.rpcversion[1] <= 10
        and plugin.rpcversion[2] < 2
    ):
        pays = plugin.rpc.listpays()["pays"]
        pays = [p for p in pays if p.get("status") == "complete"]
    else:
        pays = plugin.rpc.listpays(status="complete")["pays"]

    for r in rebalances:
        try:
            pay = next(p for p in pays if p["payment_hash"] == r["payment_hash"])
            total_amount += pay["amount_msat"]
            total_fee += pay["amount_sent_msat"] - pay["amount_msat"]
        except Exception:
            res["total_successful_rebalances"] -= 1
    res["total_rebalanced_amount"] = total_amount
    res["total_rebalance_fee"] = total_fee
    if total_amount > Millisatoshi(0):
        res["average_rebalance_fee_ppm"] = round(total_fee / total_amount * 10**6, 2)
    else:
        res["average_rebalance_fee_ppm"] = 0

    if include_avg_fees:
        avg_forward_fees = get_avg_forward_fees([1, 7, 30])
        res["average_forward_fee_ppm_1d"] = avg_forward_fees[0]
        res["average_forward_fee_ppm_7d"] = avg_forward_fees[1]
        res["average_forward_fee_ppm_30d"] = avg_forward_fees[2]

    return res


@plugin.init()
def init(options: dict, configuration: dict, plugin: Plugin, **kwargs):
    rpchelp = plugin.rpc.help().get("help")
    # detect if server cli has moved `listpeers.channels[]` to `listpeerchannels`
    # See https://github.com/ElementsProject/lightning/pull/5825
    # TODO: replace by rpc version check once v23 is released
    plugin.listpeerchannels = False
    if len([c for c in rpchelp if c["command"].startswith("listpeerchannels ")]) != 0:
        plugin.listpeerchannels = True

    # do all the stuff that needs to be done just once ...
    plugin.getinfo = plugin.rpc.getinfo()
    plugin.rpcversion = cln_parse_rpcversion(plugin.getinfo.get("version"))
    config = plugin.rpc.listconfigs()["configs"]
    plugin.cltv_final = config["cltv-final"]["value_int"]
    plugin.fee_base = Millisatoshi(config["fee-base"]["value_int"])
    plugin.fee_ppm = config["fee-per-satoshi"]["value_int"]
    plugin.mutex = threading.Lock()
    plugin.maxhops = int(options.get("rebalance-maxhops"))
    plugin.msatfactor = float(options.get("rebalance-msatfactor"))
    plugin.erringnodes = int(options.get("rebalance-erringnodes"))
    plugin.threads = int(options.get("rebalance-threads"))
    plugin.getroute = getroute_switch(options.get("rebalance-getroute"))
    plugin.rebalanceall_msg = None

    # use getroute amount_msat/msatoshi field depending on version
    plugin.msatfield = "amount_msat"
    if plugin.rpcversion[0] == 0 and plugin.rpcversion[1] < 12:
        plugin.msatfield = "msatoshi"

    plugin.log(
        f"Plugin rebalance initialized with {plugin.fee_base.to_satoshi_str()} base / {plugin.fee_ppm} ppm fee  "
        f"cltv_final:{plugin.cltv_final}  "
        f"maxhops:{plugin.maxhops}  "
        f"msatfactor:{plugin.msatfactor}  "
        f"erringnodes:{plugin.erringnodes}  "
        f"getroute:{plugin.getroute.__name__}  "
        f"threads:{plugin.threads}  "
    )


plugin.add_option(
    "rebalance-getroute",
    "iterative",
    "Getroute method for route search can be 'basic' or 'iterative'."
    "'basic': Tries all routes sequentially. "
    "'iterative': Tries shorter and bigger routes first.",
    "string",
)
plugin.add_option(
    "rebalance-maxhops",
    "5",
    "Maximum number of hops for `getroute` call. Set to 0 to disable. "
    "Note: Two hops are added for own nodes input and output channel. "
    "Note: Routes with a 8 or more hops have less than 3% success rate.",
    "string",
)

plugin.add_option(
    "rebalance-msatfactor",
    "4",
    "Will instruct `getroute` call to use higher requested capacity first. "
    "Note: This will decrease to 1 when no routes can be found.",
    "string",
)

plugin.add_option(
    "rebalance-erringnodes",
    "5",
    "Exclude nodes from routing that raised N or more errors. "
    "Note: Use 0 to disable.",
    "string",
)

plugin.add_option(
    "rebalance-threads",
    "8",
    "Number of threads used parallelly by `rebalanceall` "
    "Higher numbers increase speed and CPU consumption",
    "string",
)

plugin.run()
