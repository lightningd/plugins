#!/usr/bin/env python3
from lightning import Plugin, Millisatoshi, RpcError
import re
import time
import uuid

plugin = Plugin()


# When draining 100% we must account (not pay) for an additional HTLC fee.
# Currently there is no way of getting the exact number before the fact,
# so we try and error until it is high enough, or take the exception text.
HTLC_FEE_NUL = Millisatoshi('0sat')
HTLC_FEE_STP = Millisatoshi('10sat')
HTLC_FEE_MIN = Millisatoshi('100sat')
HTLC_FEE_MAX = Millisatoshi('100000sat')
HTLC_FEE_PAT = re.compile("^.* HTLC fee: ([0-9]+sat).*$")


def setup_routing_fees(plugin, payload, route, amount, substractfees: bool=False):
    delay = int(plugin.get_option('cltv-final'))

    amount_iter = amount
    for r in reversed(route):
        r['msatoshi'] = amount_iter.millisatoshis
        r['amount_msat'] = amount_iter
        r['delay'] = delay
        channels = plugin.rpc.listchannels(r['channel'])
        ch = next(c for c in channels.get('channels') if c['destination'] == r['id'])
        fee = Millisatoshi(ch['base_fee_millisatoshi'])
        # BOLT #7 requires fee >= fee_base_msat + ( amount_to_forward * fee_proportional_millionths / 1000000 )
        fee += (amount_iter * ch['fee_per_millionth'] + 10**6 - 1) // 10**6    # integer math trick to round up
        amount_iter += fee
        delay += ch['delay']

    # amounts have to be calculated the other way when being fee substracted
    # we took the upper loop as well for the delay parameter
    if substractfees:
        amount_iter = amount
        first = True
        for r in route:
            channels = plugin.rpc.listchannels(r['channel'])
            ch = next(c for c in channels.get('channels') if c['destination'] == r['id'])
            if not first:
                fee = Millisatoshi(ch['base_fee_millisatoshi'])
                # BOLT #7 requires fee >= fee_base_msat + ( amount_to_forward * fee_proportional_millionths / 1000000 )
                fee += (amount_iter * ch['fee_per_millionth'] + 10**6 - 1) // 10**6    # integer math trick to round up
                if fee > amount_iter:
                    raise RpcError(payload['command'], payload, {'message': 'cannot cover fees to %s %s' % (payload['command'], amount)})
                amount_iter -= fee
            first = False
            r['msatoshi'] = amount_iter.millisatoshis
            r['amount_msat'] = amount_iter


# This raises an error when a channel is not normal or peer is not connected
def get_channel(plugin, payload, peer_id, scid):
    peer = plugin.rpc.listpeers(peer_id).get('peers')[0]
    channel = next(c for c in peer['channels'] if 'short_channel_id' in c and c['short_channel_id'] == scid)
    if channel['state'] != "CHANNELD_NORMAL":
        raise RpcError(payload['command'], payload, {'message': 'Channel %s not in state CHANNELD_NORMAL, but: %s' % (scid, channel['state']) })
    if not peer['connected']:
        raise RpcError(payload['command'], payload, {'message': 'Channel %s peer is not connected.' % scid})
    return channel


def spendable_from_scid(plugin, payload, scid=None):
    if scid is None:
        scid = payload['scid']

    # only fetch funds once to reduce RPC load
    if not "funds" in payload:
        payload['funds'] = plugin.rpc.listfunds().get('channels')

    try:
        channel_funds = next(c for c in payload['funds'] if 'short_channel_id' in c and c['short_channel_id'] == scid)
    except StopIteration:
        return Millisatoshi(0), Millisatoshi(0)
    peer_id = channel_funds['peer_id']
    funds_our = Millisatoshi(channel_funds['our_amount_msat'])
    try:
        channel_peer = get_channel(plugin, payload, peer_id, scid)
    except RpcError:
        return Millisatoshi(0), Millisatoshi(0)

    # we check amounts via gossip and not wallet funds, as its more accurate
    our = Millisatoshi(channel_peer['to_us_msat'])
    total = Millisatoshi(channel_peer['total_msat'])
    our_reserve = Millisatoshi(channel_peer['our_reserve_msat'])
    their_reserve = Millisatoshi(channel_peer['their_reserve_msat'])
    their = total - our

    # reserves maybe not filled up yet
    if our < our_reserve:
        our_reserve = our
    if their < their_reserve:
        their_reserve = their

    spendable = channel_peer['spendable_msat']
    receivable = their - their_reserve
    return spendable, receivable


def peer_from_scid(plugin, payload, short_channel_id, my_id):
    channels = plugin.rpc.listchannels(short_channel_id).get('channels')
    try:
        return next(c for c in channels if c['source'] == my_id)['destination']
    except StopIteration:
        raise RpcError(payload['command'], payload, {'message': 'Cannot find peer for channel: ' + short_channel_id})


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


def test_or_set_chunks(plugin, payload, my_id):
    scid = payload['scid']
    cmd = payload['command']
    spendable, receivable = spendable_from_scid(plugin, payload)
    total = spendable + receivable
    amount = total * 0.01 * payload['percentage']

    # if capacity exceeds, limit amount to full or empty channel
    if cmd == "drain" and amount > spendable:
        amount = spendable
    if cmd == "fill" and amount > receivable:
        amount = receivable

    # get all spendable/receivables for our channels
    channels = {}
    for channel in plugin.rpc.listchannels(source=my_id).get('channels'):
        if channel['short_channel_id'] == scid:
            continue
        spend, recv = spendable_from_scid(plugin, payload, channel['short_channel_id'])
        channels[channel['short_channel_id']] = {
            'spendable' : spend,
            'receivable' : recv,
        }

    # test if selected chunks fit into other channel capacities
    if payload['chunks'] >= 1:
        chunks = payload['chunks']
        chunksize = amount / chunks
        fit = 0
        for i in channels:
            channel = channels[i]
            if cmd == "drain":
                fit += int(channel['receivable']) // int(chunksize)
            if cmd == "fill":
                fit += int(channel['spendable']) // int(chunksize)
        if fit >= chunks:
            return
        if cmd == "drain":
            raise RpcError(payload['command'], payload, {'message': 'Selected chunks (%d) will not fit incoming channel capacities.' % chunks})
        if cmd == "fill":
            raise RpcError(payload['command'], payload, {'message': 'Selected chunks (%d) will not fit outgoing channel capacities.' % chunks})


    # if chunks is 0 -> auto detect from 1 to 16 (max) chunks until amounts fit
    else:
        chunks = 0
        while chunks < 16:
            chunks += 1
            chunksize = amount / chunks
            fit = 0
            for i in channels:
                channel = channels[i]
                if cmd == "drain" and int(channel['receivable']) > 0:
                    fit += int(channel['receivable']) // int(chunksize)
                if cmd == "fill" and int(channel['spendable']) > 0:
                    fit += int(channel['spendable']) // int(chunksize)
                if fit >= chunks:
                    payload['chunks'] = chunks
                    return

        if cmd == "drain":
            raise RpcError(payload['command'], payload, {'message': 'Cannot detect required chunks to perform operation. Incoming capacity problem.'})
        if cmd == "fill":
            raise RpcError(payload['command'], payload, {'message': 'Cannot detect required chunks to perform operation. Outgoing capacity problem.'})


def cleanup(plugin, payload, error=None):
    # delete all invoices and count how many went through
    successful_chunks = 0
    for label in payload['labels']:
        try:
            plugin.rpc.delinvoice(label, 'unpaid')
        except RpcError as e:
            # race condition: waitsendpay timed out, but invoice got paid
            if 'status is paid' in e.error.get('message', ""):
                successful_chunks += 1

    if successful_chunks == payload['chunks']:
        return payload['success_msg']
    if successful_chunks > 0:
        payload['success_msg'] += ['Partially completed %d/%d chunks. Error: %s' % (successful_chunks, payload['chunks'], str(error))]
        return payload['success_msg']
    if error is None:
        error = RpcError(payload['command'], payload, {'message': 'Command failed, no chunk succeeded.'})
    raise error


def try_for_htlc_fee(plugin, payload, my_id, peer_id, amount, chunk, spendable_before):
    start_ts = int(time.time())
    label = payload['command'] + "-" + str(uuid.uuid4())
    payload['labels'] += [label]
    description = "%s %s %s%s [%d/%d]" % (payload['command'], payload['scid'], payload['percentage'], '%', chunk+1, payload['chunks'])
    invoice = plugin.rpc.invoice("any", label, description, payload['retry_for'] + 60)
    payment_hash = invoice['payment_hash']
    plugin.log("Invoice payment_hash: %s" % payment_hash)

    # exclude selected channel to prevent unwanted shortcuts
    excludes = [payload['scid']+'/0', payload['scid']+'/1']
    mychannels = plugin.rpc.listchannels(source=my_id).get('channels')
    # exclude local channels known to have too little capacity.
    # getroute currently does not do this.
    for channel in mychannels:
        if channel['short_channel_id'] == payload['scid']:
            continue  # already added few lines above
        spend, recv = spendable_from_scid(plugin, payload, channel['short_channel_id'])
        if payload['command'] == 'drain' and recv < amount:
            excludes += [channel['short_channel_id']+'/0', channel['short_channel_id']+'/1']
        if payload['command'] == 'fill' and spend < amount:
            excludes += [channel['short_channel_id']+'/0', channel['short_channel_id']+'/1']

    while int(time.time()) - start_ts < payload['retry_for']:
        if payload['command'] == 'drain':
            r = plugin.rpc.getroute(my_id, amount, riskfactor=0,
                    cltv=9, fromid=peer_id, fuzzpercent=0, exclude=excludes)
            route_out = {'id': peer_id, 'channel': payload['scid'], 'direction': int(my_id >= peer_id)}
            route = [route_out] + r['route']
            setup_routing_fees(plugin, payload, route, amount, True)
        if payload['command'] == 'fill':
            r = plugin.rpc.getroute(peer_id, amount, riskfactor=0,
                    cltv=9, fromid=my_id, fuzzpercent=0, exclude=excludes)
            route_in = {'id': my_id, 'channel': payload['scid'], 'direction': int(peer_id >= my_id)}
            route = r['route'] + [route_in]
            setup_routing_fees(plugin, payload, route, amount , False)

        fees = route[0]['amount_msat'] - route[-1]['amount_msat']

        # check fee and exclude worst channel the next time
        # NOTE: the int(msat) casts are just a workaround for outdated pylightning versions
        if fees > payload['exemptfee'] and int(fees) > int(amount) * payload['maxfeepercent'] / 100:
            worst_channel_id = find_worst_channel(route)
            if worst_channel_id is None:
                raise RpcError(payload['command'], payload, {'message': 'Insufficient fee'})
            excludes += [worst_channel_id + '/0', worst_channel_id + '/1']
            continue

        plugin.log("[%d/%d] Sending over %d hops to %s %s using %s fees" % (chunk+1, payload['chunks'], len(route), payload['command'], amount, fees))
        for r in route:
            plugin.log("    - %s  %14s  %s" % (r['id'], r['channel'], r['amount_msat']))

        try:
            plugin.rpc.sendpay(route, payment_hash, label)
            result = plugin.rpc.waitsendpay(payment_hash, payload['retry_for'] + start_ts - int(time.time()))
            if result.get('status') == 'complete':
                payload['success_msg'] += ["%dmsat sent over %d hops to %s %dmsat [%d/%d]" % (amount + fees, len(route), payload['command'], amount, chunk+1, payload['chunks'])]
                # we need to wait for gossipd to update to new state,
                # so remaining amounts will be calculated correctly for the next chunk
                spendable, _ = spendable_from_scid(plugin, payload)
                while spendable == spendable_before:
                    time.sleep(0.5)
                    spendable, _ = spendable_from_scid(plugin, payload)
                return True
            return False

        except RpcError as e:
            erring_message = e.error.get('message', '')
            erring_channel = e.error.get('data', {}).get('erring_channel')
            erring_index = e.error.get('data', {}).get('erring_index')
            erring_direction = e.error.get('data', {}).get('erring_direction')

            # detect exceeding of HTLC commitment fee
            if 'Capacity exceeded' in erring_message and erring_index == 0:
                match = HTLC_FEE_PAT.search(erring_message)
                if match:  # new servers tell htlc_fee via exception (#2691)
                    raise ValueError("htlc_fee is %s" % match.group(1))
                raise ValueError("htlc_fee unknown")

            if erring_channel == payload['scid']:
                raise RpcError(payload['command'], payload, {'message': 'Error with selected channel: %s' % erring_message})

            plugin.log("RpcError: " + str(e))
            if erring_channel is not None and erring_direction is not None:
                excludes.append(erring_channel + '/' + str(erring_direction))


def read_params(command: str, scid: str, percentage: float,
        chunks: int, maxfeepercent: float, retry_for: int, exemptfee: Millisatoshi):

    # check parameters
    if command != 'drain' and command != 'fill' and command != 'setbalance':
        raise RpcError(command, {}, {'message': 'Invalid command. Must be "drain", "fill" or "setbalance"'})
    percentage = float(percentage)
    if percentage < 0 or percentage > 100 or command != 'setbalance' and percentage == 0.0:
        raise RpcError(command, {}, {'message': 'Percentage must be between 0 and 100'})
    if chunks < 0:
        raise RpcError(command, {}, {'message': 'Negative chunks do not make sense. Try a positive value or use 0 (default) for auto-detection.'})

    # forge operation payload
    payload = {
        "command" : command,
        "scid": scid,
        "percentage": percentage,
        "chunks": chunks,
        "maxfeepercent": maxfeepercent,
        "retry_for": retry_for,
        "exemptfee": exemptfee,
        "labels" : [],
        "success_msg" : [],
    }

    # translate a 'setbalance' into respective drain or fill
    if command == 'setbalance':
        spendable, receivable = spendable_from_scid(plugin, payload)
        total = spendable + receivable
        target = total * 0.01 * payload['percentage']
        if target == spendable:
            raise RpcError(payload['command'], payload, {'message': 'target already reached, nothing to do.'})
        if spendable > target:
            payload['command'] = 'drain'
            amount = spendable - target
        else:
            payload['command'] = 'fill'
            amount = target - spendable
        payload['percentage'] = 100.0 * int(amount) / int(total)
        if payload['percentage'] == 0.0:
            raise RpcError(command, payload, {'message': 'target already reached, nothing to do.'})

    return payload


def execute(payload: dict):
    my_id = plugin.rpc.getinfo().get('id')
    peer_id = peer_from_scid(plugin, payload, payload['scid'], my_id)
    get_channel(plugin, payload, peer_id, payload['scid']) # ensures or raises error
    test_or_set_chunks(plugin, payload, my_id)
    plugin.log("%s  %s  %d%%  %d chunks" % (payload['command'], payload['scid'], payload['percentage'], payload['chunks']))

    # iterate of chunks, default just one
    for chunk in range(payload['chunks']):
        # we discover remaining capacities for each chunk,
        # as fees from previous chunks affect reserves
        spendable, receivable = spendable_from_scid(plugin, payload)
        total = spendable + receivable
        amount = total * 0.01 * payload['percentage'] / payload['chunks']

        # if capacity exceeds, limit amount to full or empty channel
        if payload['command'] == "drain" and amount > spendable:
            amount = spendable
        if payload['command'] == "fill" and amount > receivable:
            amount = receivable

        result = False
        try:
            # we need to try with different HTLC_FEE values
            # until we dont get capacity error on first hop
            htlc_fee = HTLC_FEE_NUL
            htlc_stp = HTLC_FEE_STP

            while htlc_fee < HTLC_FEE_MAX and result is False:
                # When getting close to 100% we need to account for HTLC commitment fee
                if payload['command'] == 'drain' and spendable - amount <= htlc_fee:
                    if amount < htlc_fee:
                        raise RpcError(payload['command'], payload, {'message': 'channel too low to cover fees'})
                    amount -= htlc_fee
                plugin.log("Trying... chunk:%s/%s  spendable:%s  receivable:%s  htlc_fee:%s =>  amount:%s" % (chunk+1, payload['chunks'], spendable, receivable, htlc_fee, amount))

                try:
                    result = try_for_htlc_fee(plugin, payload, my_id, peer_id, amount, chunk, spendable)
                except Exception as err:
                    if "htlc_fee unknown" in str(err):
                        if htlc_fee == HTLC_FEE_NUL:
                            htlc_fee = HTLC_FEE_MIN - HTLC_FEE_STP
                        htlc_fee += htlc_stp
                        htlc_stp *= 1.1  # exponential increase steps
                        plugin.log("Retrying with additional HTLC onchain fees: %s" % htlc_fee)
                        continue
                    if "htlc_fee is" in str(err):
                        htlc_fee = Millisatoshi(str(err)[12:])
                        plugin.log("Retrying with exact HTLC onchain fees: %s" % htlc_fee)
                        continue
                    raise err

            # If result is still false, we tried allowed htlc_fee range unsuccessfully
            if result is False:
                raise RpcError(payload['command'], payload, {'message': 'Cannot determine required htlc commitment fees.'})

        except Exception as e:
            return cleanup(plugin, payload, e)

    return cleanup(plugin, payload)


@plugin.method("drain")
def drain(plugin, scid: str, percentage: float=100, chunks: int=0, maxfeepercent: float=0.5,
        retry_for: int=60, exemptfee: Millisatoshi=Millisatoshi(5000)):
    """Draining channel liquidity with circular payments.

    Percentage defaults to 100, resulting in an empty channel.
    Chunks defaults to 0 (auto-detect).
    Use 'drain 10' to decrease a channels total balance by 10%.
    """
    payload = read_params('drain', scid, percentage, chunks, maxfeepercent, retry_for, exemptfee)
    return execute(payload)


@plugin.method("fill")
def fill(plugin, scid: str, percentage: float=100, chunks: int=0, maxfeepercent: float=0.5,
        retry_for: int=60, exemptfee: Millisatoshi=Millisatoshi(5000)):
    """Filling channel liquidity with circular payments.

    Percentage defaults to 100, resulting in a full channel.
    Chunks defaults to 0 (auto-detect).
    Use 'fill 10' to incease a channels total balance by 10%.
    """
    payload = read_params('fill', scid, percentage, chunks, maxfeepercent, retry_for, exemptfee)
    return execute(payload)

@plugin.method("setbalance")
def setbalance(plugin, scid: str, percentage: float=50, chunks: int=0, maxfeepercent: float=0.5,
        retry_for: int=60, exemptfee: Millisatoshi=Millisatoshi(5000)):
    """Brings a channels own liquidity to X percent using circular payments.

    Percentage defaults to 50, resulting in a balanced channel.
    Chunks defaults to 0 (auto-detect).
    Use 'setbalance 100' to fill a channel. Use 'setbalance 0' to drain a channel.
    """
    payload = read_params('setbalance', scid, percentage, chunks, maxfeepercent, retry_for, exemptfee)
    return execute(payload)

@plugin.init()
def init(options, configuration, plugin):
    plugin.options['cltv-final']['value'] = plugin.rpc.listconfigs().get('cltv-final')
    plugin.log("Plugin drain.py initialized")


plugin.add_option('cltv-final', 10, 'Number of blocks for final CheckLockTimeVerify expiry')
plugin.run()
