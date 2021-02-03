#!/usr/bin/env python3
from pyln.client import Plugin, Millisatoshi, RpcError
from threading import Thread, Lock
from datetime import timedelta
import time
import uuid

plugin = Plugin()
plugin.rebalance_stop = False


def setup_routing_fees(plugin, route, msatoshi):
    delay = plugin.cltv_final
    for r in reversed(route):
        r['msatoshi'] = msatoshi.millisatoshis
        r['amount_msat'] = msatoshi
        r['delay'] = delay
        channels = plugin.rpc.listchannels(r['channel'])
        ch = next(c for c in channels.get('channels') if c['destination'] == r['id'])
        fee = Millisatoshi(ch['base_fee_millisatoshi'])
        # BOLT #7 requires fee >= fee_base_msat + ( amount_to_forward * fee_proportional_millionths / 1000000 )
        fee += (msatoshi * ch['fee_per_millionth'] + 10**6 - 1) // 10**6  # integer math trick to round up
        msatoshi += fee
        delay += ch['delay']


def get_channel(plugin, payload, peer_id, scid, check_state: bool = False):
    peer = plugin.rpc.listpeers(peer_id).get('peers')[0]
    channel = next(c for c in peer['channels'] if 'short_channel_id' in c and c['short_channel_id'] == scid)
    if check_state:
        if channel['state'] != "CHANNELD_NORMAL":
            raise RpcError('rebalance', payload, {'message': 'Channel %s not in state CHANNELD_NORMAL, but: %s' % (scid, channel['state'])})
        if not peer['connected']:
            raise RpcError('rebalance', payload, {'message': 'Channel %s peer is not connected.' % scid})
    return channel


def amounts_from_scid(plugin, scid):
    channels = plugin.rpc.listfunds().get('channels')
    channel = next(c for c in channels if 'short_channel_id' in c and c['short_channel_id'] == scid)
    our_msat = Millisatoshi(channel['our_amount_msat'])
    total_msat = Millisatoshi(channel['amount_msat'])
    return our_msat, total_msat


def peer_from_scid(plugin, short_channel_id, my_node_id, payload):
    channels = plugin.rpc.listchannels(short_channel_id).get('channels')
    for ch in channels:
        if ch['source'] == my_node_id:
            return ch['destination']
    raise RpcError("rebalance", payload, {'message': 'Cannot find peer for channel: ' + short_channel_id})


def find_worst_channel(route):
    if len(route) < 4:
        return None
    start_id = 2
    worst = route[start_id]['channel']
    worst_val = route[start_id - 1]['msatoshi'] - route[start_id]['msatoshi']
    for i in range(start_id + 1, len(route) - 1):
        val = route[i - 1]['msatoshi'] - route[i]['msatoshi']
        if val > worst_val:
            worst = route[i]['channel']
            worst_val = val
    return worst


def cleanup(plugin, label, payload, success_msg, error=None):
    try:
        plugin.rpc.delinvoice(label, 'unpaid')
    except RpcError as e:
        # race condition: waitsendpay timed out, but invoice get paid
        if 'status is paid' in e.error.get('message', ""):
            return success_msg
    if error is None:
        error = RpcError("rebalance", payload, {'message': 'Rebalance failed'})
    raise error


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

    raise RpcError("rebalance", payload, {'message': 'rebalancing these channels will make things worse'})


@plugin.method("rebalance")
def rebalance(plugin, outgoing_scid, incoming_scid, msatoshi: Millisatoshi = None,
              maxfeepercent: float = 0.5, retry_for: int = 60, exemptfee: Millisatoshi = Millisatoshi(5000)):
    """Rebalancing channel liquidity with circular payments.

    This tool helps to move some msatoshis between your channels.
    """
    if msatoshi:
        msatoshi = Millisatoshi(msatoshi)
    maxfeepercent = float(maxfeepercent)
    retry_for = int(retry_for)
    exemptfee = Millisatoshi(exemptfee)
    payload = {
        "outgoing_scid": outgoing_scid,
        "incoming_scid": incoming_scid,
        "msatoshi": msatoshi,
        "maxfeepercent": maxfeepercent,
        "retry_for": retry_for,
        "exemptfee": exemptfee
    }
    my_node_id = plugin.rpc.getinfo().get('id')
    outgoing_node_id = peer_from_scid(plugin, outgoing_scid, my_node_id, payload)
    incoming_node_id = peer_from_scid(plugin, incoming_scid, my_node_id, payload)
    get_channel(plugin, payload, outgoing_node_id, outgoing_scid, True)
    get_channel(plugin, payload, incoming_node_id, incoming_scid, True)
    out_ours, out_total = amounts_from_scid(plugin, outgoing_scid)
    in_ours, in_total = amounts_from_scid(plugin, incoming_scid)
    plugin.log("Outgoing node: %s, channel: %s" % (outgoing_node_id, outgoing_scid), 'debug')
    plugin.log("Incoming node: %s, channel: %s" % (incoming_node_id, incoming_scid), 'debug')

    # If amount was not given, calculate a suitable 50/50 rebalance amount
    if msatoshi is None:
        msatoshi = calc_optimal_amount(out_ours, out_total, in_ours, in_total, payload)
        plugin.log("Estimating optimal amount %s" % msatoshi)

    # Check requested amounts are selected channels
    if msatoshi > out_ours or msatoshi > in_total - in_ours:
        raise RpcError("rebalance", payload, {'message': 'Channel capacities too low'})

    route_out = {'id': outgoing_node_id, 'channel': outgoing_scid, 'direction': int(not my_node_id < outgoing_node_id)}
    route_in = {'id': my_node_id, 'channel': incoming_scid, 'direction': int(not incoming_node_id < my_node_id)}
    start_ts = int(time.time())
    label = "Rebalance-" + str(uuid.uuid4())
    description = "%s to %s" % (outgoing_scid, incoming_scid)
    invoice = plugin.rpc.invoice(msatoshi, label, description, retry_for + 60)
    payment_hash = invoice['payment_hash']
    success_msg = ""
    try:
        excludes = []
        # excude all own channels to prevent unwanted shortcuts [out,mid,in]
        mychannels = plugin.rpc.listchannels(source=my_node_id)['channels']
        for channel in mychannels:
            excludes += [channel['short_channel_id'] + '/0', channel['short_channel_id'] + '/1']

        while int(time.time()) - start_ts < retry_for and not plugin.rebalance_stop:
            r = plugin.rpc.getroute(incoming_node_id, msatoshi, riskfactor=1, cltv=9, fromid=outgoing_node_id, exclude=excludes)
            route_mid = r['route']
            route = [route_out] + route_mid + [route_in]
            setup_routing_fees(plugin, route, msatoshi)
            fees = route[0]['amount_msat'] - msatoshi

            # check fee and exclude worst channel the next time
            # NOTE: the int(msat) casts are just a workaround for outdated pylightning versions
            if fees > exemptfee and int(fees) > int(msatoshi) * maxfeepercent / 100:
                worst_channel_id = find_worst_channel(route)
                if worst_channel_id is None:
                    raise RpcError("rebalance", payload, {'message': 'Insufficient fee'})
                excludes += [worst_channel_id + '/0', worst_channel_id + '/1']
                continue

            success_msg = {"sent": msatoshi + fees, "received": msatoshi, "fee": fees, "hops": len(route),
                           "outgoing_scid": outgoing_scid, "incoming_scid": incoming_scid, "status": "settled",
                           "message": f"{msatoshi + fees} sent over {len(route)} hops to rebalance {msatoshi}"}
            plugin.log("Sending %s over %d hops to rebalance %s" % (msatoshi + fees, len(route), msatoshi), 'debug')
            for r in route:
                plugin.log("    - %s  %14s  %s" % (r['id'], r['channel'], r['amount_msat']), 'debug')

            try:
                plugin.rpc.sendpay(route, payment_hash)
                plugin.rpc.waitsendpay(payment_hash, retry_for + start_ts - int(time.time()))
                return success_msg

            except RpcError as e:
                plugin.log("RpcError: " + str(e), 'debug')
                erring_channel = e.error.get('data', {}).get('erring_channel')
                if erring_channel == incoming_scid:
                    raise RpcError("rebalance", payload, {'message': 'Error with incoming channel'})
                if erring_channel == outgoing_scid:
                    raise RpcError("rebalance", payload, {'message': 'Error with outgoing channel'})
                erring_direction = e.error.get('data', {}).get('erring_direction')
                if erring_channel is not None and erring_direction is not None:
                    excludes.append(erring_channel + '/' + str(erring_direction))

    except Exception as e:
        plugin.log("Exception: " + str(e), 'debug')
        return cleanup(plugin, label, payload, success_msg, e)
    return cleanup(plugin, label, payload, success_msg)


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
    channels = []
    for peer in plugin.rpc.listpeers()["peers"]:
        for ch in peer["channels"]:
            if ch["state"] == "CHANNELD_NORMAL" and not ch["private"]:
                channels.append(ch)
    return channels


def check_liquidity_threshold(channels: list, threshold: Millisatoshi):
    # check if overall rebalances can be successful with this threshold
    our = sum(ch["to_us_msat"] for ch in channels)
    total = sum(ch["total_msat"] for ch in channels)
    required = Millisatoshi(0)
    for ch in channels:
        required += min(threshold, ch["total_msat"] / 2)
    return required < our and required < total - our


def binary_search(channels: list, low: Millisatoshi, high: Millisatoshi):
    if high - low < Millisatoshi("1sat"):
        return low
    next_step = (low + high) / 2
    if check_liquidity_threshold(channels, next_step):
        return binary_search(channels, next_step, high)
    else:
        return binary_search(channels, low, next_step)


def get_enough_liquidity_threshold(channels: list):
    biggest_channel = max(channels, key=lambda ch: ch["total_msat"])
    max_threshold = binary_search(channels, Millisatoshi(0), biggest_channel["total_msat"] / 2)
    return max_threshold / 2


def get_ideal_ratio(channels: list, enough_liquidity: Millisatoshi):
    # ideal liquidity ratio for big channels:
    # small channels should have a 50/50 liquidity ratio to be usable
    # and big channels can store the remaining liquidity above the threshold
    assert len(channels) > 0
    our = sum(ch["to_us_msat"] for ch in channels)
    total = sum(ch["total_msat"] for ch in channels)
    chs = list(channels)  # get a copy!
    while len(chs) > 0:
        ratio = int(our) / int(total)
        smallest_channel = min(chs, key=lambda ch: ch["total_msat"])
        if smallest_channel["total_msat"] * min(ratio, 1 - ratio) > enough_liquidity:
            break
        min_liquidity = min(smallest_channel["total_msat"] / 2, enough_liquidity)
        diff = smallest_channel["total_msat"] * ratio
        diff = max(diff, min_liquidity)
        diff = min(diff, smallest_channel["total_msat"] - min_liquidity)
        our -= diff
        total -= smallest_channel["total_msat"]
        chs.remove(smallest_channel)
    assert 0 <= ratio and ratio <= 1
    return ratio


def feeadjust_would_be_nice(plugin: Plugin):
    commands = [c for c in plugin.rpc.help().get("help") if c["command"].split()[0] == "feeadjust"]
    if len(commands) == 1:
        msg = plugin.rpc.feeadjust()
        plugin.log(f"Feeadjust succeeded: {msg}")
    else:
        plugin.log("The feeadjuster plugin would be useful here")


def get_max_amount(i: int, plugin: Plugin):
    return max(plugin.min_amount, plugin.enough_liquidity / (4**(i + 1)))


def get_max_fee(plugin: Plugin, msat: Millisatoshi):
    # TODO: sanity check
    return (plugin.fee_base + msat * plugin.fee_ppm / 10**6) * plugin.feeratio


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


def liquidity_info(channel, enough_liquidity: Millisatoshi, ideal_ratio: float):
    liquidity = {
        "our": channel["to_us_msat"],
        "their": channel["total_msat"] - channel["to_us_msat"],
        "min": min(enough_liquidity, channel["total_msat"] / 2),
        "max": max(a_minus_b(channel["total_msat"], enough_liquidity), channel["total_msat"] / 2),
        "ideal": {}
    }
    liquidity["ideal"]["our"] = min(max(channel["total_msat"] * ideal_ratio, liquidity["min"]), liquidity["max"])
    liquidity["ideal"]["their"] = min(max(channel["total_msat"] * (1 - ideal_ratio), liquidity["min"]), liquidity["max"])
    return liquidity


def maybe_rebalance_pairs(plugin: Plugin, ch1, ch2, failed_pairs: list):
    scid1 = ch1["short_channel_id"]
    scid2 = ch2["short_channel_id"]
    result = {"success": False, "fee_spent": Millisatoshi(0)}
    if scid1 + ":" + scid2 in failed_pairs:
        return result
    i = 0
    while not plugin.rebalance_stop:
        liquidity1 = liquidity_info(ch1, plugin.enough_liquidity, plugin.ideal_ratio)
        liquidity2 = liquidity_info(ch2, plugin.enough_liquidity, plugin.ideal_ratio)
        amount1 = min(must_send(liquidity1), could_receive(liquidity2))
        amount2 = min(should_send(liquidity1), should_receive(liquidity2))
        amount3 = min(could_send(liquidity1), must_receive(liquidity2))
        amount = max(amount1, amount2, amount3)
        if amount < plugin.min_amount:
            return result
        amount = min(amount, get_max_amount(i, plugin))
        maxfee = get_max_fee(plugin, amount)
        plugin.log(f"Try to rebalance: {scid1} -> {scid2}; amount={amount}; maxfee={maxfee}")
        start_ts = time.time()
        try:
            res = rebalance(plugin, outgoing_scid=scid1, incoming_scid=scid2, msatoshi=amount, maxfeepercent=0, retry_for=1200, exemptfee=maxfee)
        except Exception:
            failed_pairs.append(scid1 + ":" + scid2)
            # rebalance failed, let's try with a smaller amount
            while (get_max_amount(i, plugin) >= amount and
                   get_max_amount(i, plugin) != get_max_amount(i + 1, plugin)):
                i += 1
            if amount > get_max_amount(i, plugin):
                continue
            return result
        elapsed_time = timedelta(seconds=time.time() - start_ts)
        res["elapsed_time"] = str(elapsed_time)[:-3]
        plugin.log(f"Rebalance succeeded: {res}")
        result["success"] = True
        result["fee_spent"] += res["fee"]
        # refresh channels
        time.sleep(10)
        ch1 = get_chan(plugin, scid1)
        assert ch1 is not None
        ch2 = get_chan(plugin, scid2)
        assert ch2 is not None
    return result


def maybe_rebalance_once(plugin: Plugin, failed_pairs: list):
    channels = get_open_channels(plugin)
    for ch1 in channels:
        for ch2 in channels:
            if ch1 == ch2:
                continue
            result = maybe_rebalance_pairs(plugin, ch1, ch2, failed_pairs)
            if result["success"] or plugin.rebalance_stop:
                return result
    return {"success": False, "fee_spent": Millisatoshi(0)}


def feeadjuster_toggle(plugin: Plugin, new_value: bool):
    commands = [c for c in plugin.rpc.help().get("help") if c["command"].split()[0] == "feeadjuster-toggle"]
    if len(commands) == 1:
        msg = plugin.rpc.feeadjuster_toggle(new_value)
        return msg["forward_event_subscription"]["previous"]
    else:
        return True


def rebalanceall_thread(plugin: Plugin):
    if not plugin.mutex.acquire(blocking=False):
        return
    try:
        start_ts = time.time()
        feeadjuster_state = feeadjuster_toggle(plugin, False)
        channels = get_open_channels(plugin)
        plugin.enough_liquidity = get_enough_liquidity_threshold(channels)
        plugin.ideal_ratio = get_ideal_ratio(channels, plugin.enough_liquidity)
        plugin.log(f"Automatic rebalance is running with enough liquidity threshold: {plugin.enough_liquidity}, "
                   f"ideal liquidity ratio: {plugin.ideal_ratio * 100:.2f}%, "
                   f"min rebalancable amount: {plugin.min_amount}, "
                   f"feeratio: {plugin.feeratio}")
        failed_pairs = []
        success = 0
        fee_spent = Millisatoshi(0)
        while not plugin.rebalance_stop:
            result = maybe_rebalance_once(plugin, failed_pairs)
            if not result["success"]:
                break
            success += 1
            fee_spent += result["fee_spent"]
        feeadjust_would_be_nice(plugin)
        feeadjuster_toggle(plugin, feeadjuster_state)
        elapsed_time = timedelta(seconds=time.time() - start_ts)
        plugin.log(f"Automatic rebalance finished: {success} successful rebalance, {fee_spent} fee spent, it took {str(elapsed_time)[:-3]}")
    finally:
        plugin.mutex.release()


@plugin.method("rebalanceall")
def rebalanceall(plugin: Plugin, min_amount: Millisatoshi = Millisatoshi("50000sat"), feeratio: float = 0.5):
    """Rebalance all unbalanced channels if possible for a very low fee.
    Default minimum rebalancable amount is 50000sat. Default feeratio = 0.5, half of our node's default fee.
    To be economical, it tries to fix the liquidity cheaper than it can be ruined by transaction forwards.
    It may run for a long time (hours) in the background, but can be stopped with the rebalancestop method.
    """
    if plugin.mutex.locked():
        return {"message": "Rebalance is already running, this may take a while. To stop it use the cli method 'rebalancestop'."}
    if len(get_open_channels(plugin)) <= 1:
        return {"message": "Error: Not enough open channels to balance anything"}
    plugin.feeratio = float(feeratio)
    plugin.min_amount = Millisatoshi(min_amount)
    t = Thread(target=rebalanceall_thread, args=(plugin, ))
    t.start()
    return {"message": f"Rebalance started with min rebalancable amount: {plugin.min_amount}, feeratio: {plugin.feeratio}"}


@plugin.method("rebalancestop")
def rebalancestop(plugin: Plugin):
    """It stops the ongoing rebalanceall.
    """
    if not plugin.mutex.locked():
        return {"message": "No rebalance is running, nothing to stop"}
    plugin.rebalance_stop = True
    plugin.mutex.acquire(blocking=True)
    plugin.rebalance_stop = False
    plugin.mutex.release()
    return {"message": "Rebalance stopped"}


@plugin.init()
def init(options, configuration, plugin):
    config = plugin.rpc.listconfigs()
    plugin.cltv_final = config.get("cltv-final")
    plugin.fee_base = Millisatoshi(config.get("fee-base"))
    plugin.fee_ppm = config.get("fee-per-satoshi")
    plugin.mutex = Lock()
    plugin.log(f"Plugin rebalance initialized with {plugin.fee_base} base / {plugin.fee_ppm} ppm fee, "
               f"cltv_final: {plugin.cltv_final}")


plugin.run()
