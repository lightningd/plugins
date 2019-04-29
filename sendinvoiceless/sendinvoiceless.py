#!/usr/bin/env python3
from lightning import Plugin, Millisatoshi, RpcError
import time
import uuid

plugin = Plugin()

def setup_routing_fees(plugin, route, msatoshi, payload):
    delay = int(plugin.get_option('cltv-final'))
    for r in reversed(route):
        r['msatoshi'] = r['amount_msat'] = msatoshi
        r['delay'] = delay
        channels = plugin.rpc.listchannels(r['channel'])
        for ch in channels.get('channels'):
            if ch['destination'] == r['id']:
                fee = Millisatoshi(ch['base_fee_millisatoshi'])
                fee += msatoshi * ch['fee_per_millionth'] // 1000000
                if ch['source'] == payload['nodeid']:
                    if fee <= payload['msatoshi']:
                        fee = payload['msatoshi']
                    else:
                        raise RpcError("sendinvoiceless", payload, {'message': 'Insufficient sending amount'})
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


def sendinvoiceless_fail(plugin, label, payload, success_msg, error=None):
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
def sendinvoiceless(plugin, nodeid, msatoshi: Millisatoshi, maxfeepercent="0.5",
                    retry_for=60, exemptfee: Millisatoshi=Millisatoshi(5000)):
    """Invoiceless payment with circular routes.

    This tool sends some msatoshis without needing to have an invoice from the receiving node.

    """
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
    invoice = plugin.rpc.invoice(change, label, description, int(retry_for) + 60)
    payment_hash = invoice['payment_hash']
    plugin.log("Invoice payment_hash: %s" % payment_hash)
    success_msg = ""
    try:
        excludes = []
        start_ts = int(time.time())
        while int(time.time()) - start_ts < int(retry_for):
            forth = plugin.rpc.getroute(nodeid, msatoshi + change, riskfactor=10, exclude=excludes)
            back = plugin.rpc.getroute(myid, change, riskfactor=10, fromid=nodeid, exclude=excludes)
            route = forth['route'] + back['route']
            setup_routing_fees(plugin, route, change, payload)
            fees = route[0]['msatoshi'] - route[-1]['msatoshi'] - msatoshi
            # Next line would be correct, but must be fixed to work around #2601 - cleanup when merged
            # if fees > exemptfee and fees > msatoshi * float(maxfeepercent) / 100:
            if fees > exemptfee and int(fees) > int(msatoshi) * float(maxfeepercent) / 100:
                worst_channel = find_worst_channel(route, nodeid)
                if worst_channel is None:
                    raise RpcError("sendinvoiceless", payload, {'message': 'Insufficient fee'})
                excludes.append(worst_channel)
                continue
            try:
                plugin.log("Sending %s over %d hops to deliver %s and bring back %s" %
                           (route[0]['msatoshi'], len(route), msatoshi, change))
                for r in route:
                    plugin.log("Node: %s, channel: %13s, %s" % (r['id'], r['channel'], r['msatoshi']))
                success_msg = "%d msat delivered with %d msat fee over %d hops" % (msatoshi, fees, len(route))
                plugin.rpc.sendpay(route, payment_hash)
                plugin.rpc.waitsendpay(payment_hash, int(retry_for) + start_ts - int(time.time()))
                return success_msg
            except RpcError as e:
                plugin.log("RpcError: " + str(e))
                erring_channel = e.error.get('data', {}).get('erring_channel')
                erring_direction = e.error.get('data', {}).get('erring_direction')
                if erring_channel is not None and erring_direction is not None:
                    excludes.append(erring_channel + '/' + str(erring_direction))
    except Exception as e:
        plugin.log("Exception: " + str(e))
        return sendinvoiceless_fail(plugin, label, payload, success_msg, e)
    return sendinvoiceless_fail(plugin, label, payload, success_msg)


@plugin.init()
def init(options, configuration, plugin):
    plugin.options['cltv-final']['value'] = plugin.rpc.listconfigs().get('cltv-final')
    plugin.log("Plugin sendinvoiceless.py initialized")


plugin.add_option('cltv-final', 10, 'Number of blocks for final CheckLockTimeVerify expiry')
plugin.run()
