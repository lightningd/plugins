#!/usr/bin/env python3
from lightning import Plugin, Millisatoshi, RpcError
from datetime import datetime
import time
import uuid

plugin = Plugin()

def setup_routing_fees(plugin, route, msatoshi, payload):
    delay = int(plugin.get_option('cltv-final'))
    for r in reversed(route):
        r['msatoshi'] = msatoshi.millisatoshis
        r['amount_msat'] = msatoshi
        r['delay'] = delay
        channels = plugin.rpc.listchannels(r['channel'])
        ch = next(c for c in channels.get('channels') if c['destination'] == r['id'])
        fee = Millisatoshi(ch['base_fee_millisatoshi'])
        # BOLT #7 requires fee >= fee_base_msat + ( amount_to_forward * fee_proportional_millionths / 1000000 )
        fee += (msatoshi * ch['fee_per_millionth'] + 10**6 - 1) // 10**6       # integer math trick to round up
        if ch['source'] == payload['nodeid']:
            fee += payload['msatoshi']
        msatoshi += fee
        delay += ch['delay']
        r['direction'] = int(ch['channel_flags']) % 2


def find_worst_channel(route, nodeid):
    worst = None
    worst_val = Millisatoshi(0)
    for i in range(1, len(route)):
        if route[i - 1]['id'] == nodeid:
            continue
        val = route[i - 1]['msatoshi'] - route[i]['msatoshi']
        if val > worst_val:
            worst = route[i]['channel'] + '/' + str(route[i]['direction'])
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
        error = RpcError("sendinvoiceless", payload, {'message': 'Sending failed'})
    raise error


@plugin.method("sendinvoiceless")
def sendinvoiceless(plugin, nodeid, msatoshi: Millisatoshi, maxfeepercent: float=0.5,
                    retry_for: int=60, exemptfee: Millisatoshi=Millisatoshi(5000)):
    """Send invoiceless payments with circular routes.
    This tool sends some msatoshis without needing to have an invoice from the receiving node.
    """
    msatoshi = Millisatoshi(msatoshi)
    maxfeepercent = float(maxfeepercent)
    retry_for = int(retry_for)
    exemptfee = Millisatoshi(exemptfee)
    payload = {
        "nodeid": nodeid,
        "msatoshi": msatoshi,
        "maxfeepercent": maxfeepercent,
        "retry_for": retry_for,
        "exemptfee": exemptfee
    }
    myid = plugin.rpc.getinfo().get('id')
    label = "InvoicelessChange-" + str(uuid.uuid4())
    description = "Sending %s to %s" % (msatoshi, nodeid)
    change = Millisatoshi(1000)
    invoice = plugin.rpc.invoice(change, label, description, retry_for + 60)
    payment_hash = invoice['payment_hash']
    plugin.log("Invoice payment_hash: %s" % payment_hash)
    success_msg = ""
    try:
        excludes = []
        start_ts = int(time.time())
        while int(time.time()) - start_ts < retry_for:
            forth = plugin.rpc.getroute(nodeid, msatoshi + change, riskfactor=10, exclude=excludes)
            back = plugin.rpc.getroute(myid, change, riskfactor=10, fromid=nodeid, exclude=excludes)
            route = forth['route'] + back['route']
            setup_routing_fees(plugin, route, change, payload)
            fees = route[0]['amount_msat'] - route[-1]['amount_msat'] - msatoshi

            # check fee and exclude worst channel the next time
            # NOTE: the int(msat) casts are just a workaround for outdated pylightning versions
            if fees > exemptfee and int(fees) > int(msatoshi) * maxfeepercent / 100:
                worst_channel = find_worst_channel(route, nodeid)
                if worst_channel is None:
                    raise RpcError("sendinvoiceless", payload, {'message': 'Insufficient fee'})
                excludes.append(worst_channel)
                continue

            success_msg = "%d msat delivered with %d msat fee over %d hops" % (msatoshi, fees, len(route))
            plugin.log("Sending %s over %d hops to send %s and return %s" % (route[0]['msatoshi'], len(route), msatoshi, change))
            for r in route:
                plugin.log("    - %s  %14s  %s" % (r['id'], r['channel'], r['amount_msat']))

            try:
                plugin.rpc.sendpay(route, payment_hash)
                plugin.rpc.waitsendpay(payment_hash, retry_for + start_ts - int(time.time()))
                return success_msg

            except RpcError as e:
                plugin.log("RpcError: " + str(e))
                erring_channel = e.error.get('data', {}).get('erring_channel')
                erring_direction = e.error.get('data', {}).get('erring_direction')
                if erring_channel is not None and erring_direction is not None:
                    excludes.append(erring_channel + '/' + str(erring_direction))

    except Exception as e:
        plugin.log("Exception: " + str(e))
        return cleanup(plugin, label, payload, success_msg, e)
    return cleanup(plugin, label, payload, success_msg)


@plugin.method("receivedinvoiceless")
def receivedinvoiceless(plugin, min_amount: Millisatoshi=Millisatoshi(10000)):
    """
    List payments received via sendinvoiceless from other nodes.
    """

    mynodeid = plugin.rpc.getinfo()['id']
    mychannels = plugin.rpc.listchannels(source=mynodeid)['channels']
    forwards = plugin.rpc.listforwards()['forwards']
    default_fees = {
        'base' : int(plugin.get_option('fee-base')),
        'ppm' : int(plugin.get_option('fee-per-satoshi'))}

    # build a mapping of mychannel fees
    # <scid -> {base, ppm}>
    myfees = {}
    for channel in mychannels:
        scid = channel['short_channel_id']
        myfees[scid] = {
            'base' : channel['base_fee_millisatoshi'],
            'ppm'  : channel['fee_per_millionth']}

    # loop through settled forwards and check for overpaid routings
    result = []
    for forward in forwards:
        if forward['status'] != "settled":
            continue

        # for old channel, we dont know fees anymore, use defaults
        scid = forward['out_channel']
        fees = myfees.get(scid, default_fees)
        fee_paid = forward['fee']
        fee_required = int(forward['out_msatoshi'] * fees['ppm'] * 10**-6 + fees['base'])

        if fee_paid > fee_required:
            amount = Millisatoshi(fee_paid - fee_required)

            # fess can sometimes not be exact when channel fees changed in the past, filter those
            if amount < min_amount:
                continue

            entry = {'amount_msat' : amount, 'amount_btc' : amount.to_btc_str()}

            # old lightningd versions may not support received_time yet
            if 'resolved_time' in forward:
                time_secs = int(forward['resolved_time'])
                time_str = datetime.utcfromtimestamp(time_secs).strftime('%Y-%m-%d %H:%M:%S (UTC)')
                entry['resolved_time'] = forward['resolved_time']
                entry['timestamp'] = time_str

            result.append(entry)

    return result


@plugin.init()
def init(options, configuration, plugin):
    plugin.options['cltv-final']['value'] = plugin.rpc.listconfigs().get('cltv-final')
    plugin.options['fee-base']['value'] = plugin.rpc.listconfigs().get('fee-base')
    plugin.options['fee-per-satoshi']['value'] = plugin.rpc.listconfigs().get('fee-per-satoshi')
    plugin.log("Plugin sendinvoiceless.py initialized")


plugin.add_option('cltv-final', 10, 'Number of blocks for final CheckLockTimeVerify expiry')
plugin.add_option('fee-base', None, 'The routing base fee in msat. Will be derived automatically via rpc.listconfigs()')
plugin.add_option('fee-per-satoshi', None, 'The routing fee ppm. Will be derived automatically via rpc.listconfigs()')
plugin.run()
