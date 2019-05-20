#!/usr/bin/env python3
from lightning import Plugin, Millisatoshi, RpcError
import time
import uuid

plugin = Plugin()


def setup_routing_fees(plugin, route, msatoshi):
    delay = int(plugin.get_option('cltv-final'))
    for r in reversed(route):
        r['msatoshi'] = r['amount_msat'] = msatoshi
        r['delay'] = delay
        channels = plugin.rpc.listchannels(r['channel'])
        for ch in channels.get('channels'):
            if ch['destination'] == r['id']:
                fee = Millisatoshi(ch['base_fee_millisatoshi'])
                fee += msatoshi * ch['fee_per_millionth'] // 1000000
                msatoshi += fee
                delay += ch['delay']


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


def rebalance_fail(plugin, label, payload, success_msg, error=None):
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
# TODO: their_reserve_msat our_reserve_msat spendable_msat
def calc_optimal_amount(out_ours, out_total, in_ours, in_total, payload):
    out_ours, out_total = int(out_ours), int(out_total)
    in_ours, in_total = int(in_ours), int(in_total)

    in_theirs = in_total - in_ours
    vo = int(out_ours - (out_total/2))
    vi = int((in_total/2) - in_ours)

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
def rebalance(plugin, outgoing_scid, incoming_scid, msatoshi: Millisatoshi=None,
              maxfeepercent="0.5", retry_for="60", exemptfee: Millisatoshi=Millisatoshi(5000)):
    """Rebalancing channel liquidity with circular payments.

    This tool helps to move some msatoshis between your channels.

    """
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
    plugin.log("Outgoing node: %s, channel: %s" % (outgoing_node_id, outgoing_scid))
    plugin.log("Incoming node: %s, channel: %s" % (incoming_node_id, incoming_scid))

    # If amount was not given, calculate a suitable 50/50 rebalance amount
    if msatoshi is None:
        out_ours, out_total = amounts_from_scid(plugin, outgoing_scid)
        in_ours, in_total = amounts_from_scid(plugin, incoming_scid)
        msatoshi = calc_optimal_amount(out_ours, out_total, in_ours, in_total, payload)
        plugin.log("Estimating optimal amount %s" % msatoshi)

    route_out = {'id': outgoing_node_id, 'channel': outgoing_scid}
    route_in = {'id': my_node_id, 'channel': incoming_scid}
    start_ts = int(time.time())
    label = "Rebalance-" + str(uuid.uuid4())
    description = "%s to %s" % (outgoing_scid, incoming_scid)
    invoice = plugin.rpc.invoice(msatoshi, label, description, int(retry_for) + 60)
    payment_hash = invoice['payment_hash']
    plugin.log("Invoice payment_hash: %s" % payment_hash)
    success_msg = ""
    try:
        excludes = []
        mychannels = plugin.rpc.listchannels(source=my_node_id)['channels']
        for channel in mychannels:
            excludes += [channel['short_channel_id'] + '/0', channel['short_channel_id'] + '/1']
        while int(time.time()) - start_ts < int(retry_for):
            r = plugin.rpc.getroute(incoming_node_id, msatoshi, riskfactor=1, cltv=9, fromid=outgoing_node_id,
                                    exclude=excludes)
            route_mid = r['route']
            route = [route_out] + route_mid + [route_in]
            setup_routing_fees(plugin, route, msatoshi)
            fees = route[0]['msatoshi'] - route[-1]['msatoshi']
            # NOTE: the int(msat) casts are just a workaround for outdated pylightning versions
            if fees > exemptfee and int(fees) > int(msatoshi) * float(maxfeepercent) / 100:
                worst_channel_id = find_worst_channel(route)
                if worst_channel_id is None:
                    raise RpcError("rebalance", payload, {'message': 'Insufficient fee'})
                excludes += [worst_channel_id + '/0', worst_channel_id + '/1']
                continue
            try:
                plugin.log("Sending %s over %d hops to rebalance %s" % (msatoshi + fees, len(route), msatoshi))
                for r in route:
                    plugin.log("Node: %s, channel: %13s, %s" % (r['id'], r['channel'], r['msatoshi']))
                success_msg = "%d msat sent over %d hops to rebalance %d msat" % (msatoshi + fees, len(route), msatoshi)
                plugin.rpc.sendpay(route, payment_hash)
                plugin.rpc.waitsendpay(payment_hash, int(retry_for) + start_ts - int(time.time()))
                return success_msg
            except RpcError as e:
                plugin.log("RpcError: " + str(e))
                erring_channel = e.error.get('data', {}).get('erring_channel')
                if erring_channel == incoming_scid:
                    raise RpcError("rebalance", payload, {'message': 'Error with incoming channel'})
                if erring_channel == outgoing_scid:
                    raise RpcError("rebalance", payload, {'message': 'Error with outgoing channel'})
                erring_direction = e.error.get('data', {}).get('erring_direction')
                if erring_channel is not None and erring_direction is not None:
                    excludes.append(erring_channel + '/' + str(erring_direction))
    except Exception as e:
        plugin.log("Exception: " + str(e))
        return rebalance_fail(plugin, label, payload, success_msg, e)
    return rebalance_fail(plugin, label, payload, success_msg)


@plugin.init()
def init(options, configuration, plugin):
    plugin.options['cltv-final']['value'] = plugin.rpc.listconfigs().get('cltv-final')
    plugin.log("Plugin rebalance.py initialized")


plugin.add_option('cltv-final', 10, 'Number of blocks for final CheckLockTimeVerify expiry')
plugin.run()
