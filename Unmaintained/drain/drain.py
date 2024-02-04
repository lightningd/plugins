#!/usr/bin/env python3
from clnutils import cln_parse_rpcversion
from pyln.client import Plugin, Millisatoshi, RpcError
from utils import get_ours, wait_ours
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
HTLC_FEE_EST = Millisatoshi('3000sat')
HTLC_FEE_PAT = re.compile("^.* HTLC fee: ([0-9]+sat).*$")


# The route msat helpers are needed because older versions of cln
# had different msat/msatoshi fields with different types Millisatoshi/int
def route_set_msat(r, msat):
    if plugin.rpcversion[0] == 0 and plugin.rpcversion[1] < 12:
        r[plugin.msatfield] = msat.millisatoshis
        r['amount_msat'] = Millisatoshi(msat)
    else:
        r[plugin.msatfield] = Millisatoshi(msat)


def route_get_msat(r):
    return Millisatoshi(r[plugin.msatfield])


def setup_routing_fees(payload, route, amount, substractfees: bool = False):
    delay = plugin.cltv_final

    amount_iter = amount
    for r in reversed(route):
        route_set_msat(r, amount_iter)
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
                    raise RpcError(payload['command'], payload, {'message': 'Cannot cover fees to %s %s' % (payload['command'], amount)})
                amount_iter -= fee
            first = False
            route_set_msat(r, amount_iter)


# This raises an error when a channel is not normal or peer is not connected
def get_channel(payload, peer_id, scid=None):
    if scid is None:
        scid = payload['scid']

    # from versions 23 and onwards we have `listpeers` and `listpeerchannels`
    # if plugin.rpcversion[0] >= 23:
    if plugin.listpeerchannels:  # FIXME: replace by rpcversion check (see above) once 23 is released
        channels = plugin.rpc.listpeerchannels(peer_id)["channels"]
        if len(channels) == 0:
            raise RpcError(payload['command'], payload, {'message': 'Cannot find channels for peer %s' % (peer_id)})
        try:
            channel = next(c for c in channels if 'short_channel_id' in c and c['short_channel_id'] == scid)
        except StopIteration:
            raise RpcError(payload['command'], payload, {'message': 'Cannot find channel for peer %s with scid %s' % (peer_id, scid)})
        if channel['state'] != "CHANNELD_NORMAL":
            raise RpcError(payload['command'], payload, {'message': 'Channel %s: not in state CHANNELD_NORMAL, but: %s' % (scid, channel['state'])})
        if not channel['peer_connected']:
            raise RpcError(payload['command'], payload, {'message': 'Channel %s: peer is not connected.' % scid})
        return channel

    peers = plugin.rpc.listpeers(peer_id)['peers']
    if len(peers) == 0:
        raise RpcError(payload['command'], payload, {'message': 'Cannot find peer %s' % peer_id})
    try:
        channel = next(c for c in peers[0]['channels'] if 'short_channel_id' in c and c['short_channel_id'] == scid)
    except StopIteration:
        raise RpcError(payload['command'], payload, {'message': 'Cannot find channel %s for peer %s' % (scid, peer_id)})
    if channel['state'] != "CHANNELD_NORMAL":
        raise RpcError(payload['command'], payload, {'message': 'Channel %s not in state CHANNELD_NORMAL, but: %s' % (scid, channel['state'])})
    if not peers[0]['connected']:
        raise RpcError(payload['command'], payload, {'message': 'Channel %s peer is not connected.' % scid})
    return channel


def spendable_from_scid(payload, scid=None, _raise=False):
    if scid is None:
        scid = payload['scid']

    peer_id = peer_from_scid(payload, scid)
    try:
        channel = get_channel(payload, peer_id, scid)
    except RpcError as e:
        if _raise:
            raise e
        return Millisatoshi(0), Millisatoshi(0)

    # we check amounts via gossip and not wallet funds, as its more accurate
    our = Millisatoshi(channel['to_us_msat'])
    total = Millisatoshi(channel['total_msat'])
    our_reserve = Millisatoshi(channel['our_reserve_msat'])
    their_reserve = Millisatoshi(channel['their_reserve_msat'])
    their = total - our

    # reserves maybe not filled up yet
    if our < our_reserve:
        our_reserve = our
    if their < their_reserve:
        their_reserve = their

    spendable = channel['spendable_msat']
    receivable = channel.get('receivable_msat')

    # receivable_msat was added with the 0.8.2 release, have a fallback
    if not receivable:
        receivable = their - their_reserve
        # we also need to subsctract a possible commit tx fee
        if receivable >= HTLC_FEE_EST:
            receivable -= HTLC_FEE_EST
    return spendable, receivable


def peer_from_scid(payload, scid=None):
    if scid is None:
        scid = payload['scid']

    channels = plugin.rpc.listchannels(scid).get('channels')
    try:
        return next(c for c in channels if c['source'] == payload['my_id'])['destination']
    except StopIteration:
        raise RpcError(payload['command'], payload, {'message': 'Cannot find peer for channel: ' + scid})


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


def test_or_set_chunks(payload):
    scid = payload['scid']
    cmd = payload['command']
    spendable, receivable = spendable_from_scid(payload)
    total = spendable + receivable
    amount = Millisatoshi(int(int(total) * (0.01 * payload['percentage'])))

    # if capacity exceeds, limit amount to full or empty channel
    if cmd == "drain" and amount > spendable:
        amount = spendable
    if cmd == "fill" and amount > receivable:
        amount = receivable
    if amount == Millisatoshi(0):
        raise RpcError(payload['command'], payload, {'message': 'Cannot detect required chunks to perform operation. Amount would be 0msat.'})

    # get all spendable/receivables for our channels
    channels = {}
    for channel in payload['mychannels']:
        if channel['short_channel_id'] == scid:
            continue
        try:
            spend, recv = spendable_from_scid(payload, channel['short_channel_id'], True)
        except RpcError:
            continue
        channels[channel['short_channel_id']] = {
            'spendable': spend,
            'receivable': recv,
        }
    if len(channels) == 0:
        raise RpcError(payload['command'], payload, {'message': 'Not enough usable channels to perform cyclic routing.'})

    # test if selected chunks fit into other channel capacities
    chunks = payload['chunks']
    if chunks > 0:
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


def cleanup(payload, error=None):
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
        error = RpcError(payload['command'], payload, {'message': 'Partially completed %d/%d chunks. Error: %s' % (successful_chunks, payload['chunks'], str(error))})
    if error is None:
        error = RpcError(payload['command'], payload, {'message': 'Command failed, no chunk succeeded.'})
    raise error


def try_for_htlc_fee(payload, peer_id, amount, chunk, spendable_before):
    start_ts = int(time.time())
    remaining_secs = max(0, payload['start_ts'] + payload['retry_for'] - start_ts)
    remaining_chunks = payload['chunks'] - chunk
    retry_for = int(remaining_secs / remaining_chunks)
    my_id = payload['my_id']
    label = f"{payload['command']}-{uuid.uuid4()}"
    payload['labels'] += [label]
    description = "%s %s %s%s [%d/%d]" % (payload['command'], payload['scid'], payload['percentage'], '%', chunk + 1, payload['chunks'])
    invoice = plugin.rpc.invoice("any", label, description, retry_for + 60)
    payment_hash = invoice['payment_hash']
    # The requirement for payment_secret coincided with its addition to the invoice output.
    payment_secret = invoice.get('payment_secret')
    plugin.log("Invoice payment_hash: %s" % payment_hash)

    # exclude selected channel to prevent unwanted shortcuts
    excludes = [f"{payload['scid']}/0", f"{payload['scid']}/1"]

    # exclude local channels known to have too little capacity.
    for channel in payload['mychannels']:
        if channel['short_channel_id'] == payload['scid']:
            continue  # already added few lines above
        spend, recv = spendable_from_scid(payload, channel['short_channel_id'])
        if payload['command'] == 'drain' and recv < amount or payload['command'] == 'fill' and spend < amount:
            excludes.append(f"{channel['short_channel_id']}/0")
            excludes.append(f"{channel['short_channel_id']}/1")

    while int(time.time()) - start_ts < retry_for:
        if payload['command'] == 'drain':
            r = plugin.rpc.getroute(my_id, amount, fromid=peer_id, exclude=excludes,
                                    maxhops=6, riskfactor=10, cltv=9, fuzzpercent=0)
            route_out = {'id': peer_id, 'channel': payload['scid'], 'direction': int(my_id >= peer_id)}
            route = [route_out] + r['route']
            setup_routing_fees(payload, route, amount, True)
        if payload['command'] == 'fill':
            r = plugin.rpc.getroute(peer_id, amount, fromid=my_id, exclude=excludes,
                                    maxhops=6, riskfactor=10, cltv=9, fuzzpercent=0)
            route_in = {'id': my_id, 'channel': payload['scid'], 'direction': int(peer_id >= my_id)}
            route = r['route'] + [route_in]
            setup_routing_fees(payload, route, amount, False)

        # check fee and exclude worst channel the next time
        # NOTE: the int(msat) casts are just a workaround for outdated pylightning versions
        fees = route_get_msat(route[0]) - route_get_msat(route[-1])
        if fees > payload['exemptfee'] and int(fees) > int(amount) * payload['maxfeepercent'] / 100:
            worst_channel = find_worst_channel(route)
            if worst_channel is None:
                raise RpcError(payload['command'], payload, {'message': 'Insufficient fee'})
            excludes.append(f"{worst_channel['channel']}/{worst_channel['direction']}")
            continue

        plugin.log(f"[{chunk + 1}/{payload['chunks']}] Sending over "
                   f"{len(route)} hops to {payload['command']} {amount} using "
                   f"{fees} fees", 'debug')
        for r in route:
            plugin.log("    - %s  %14s  %s" % (r['id'], r['channel'], route_get_msat(r)), 'debug')

        try:
            ours = get_ours(plugin, payload['scid'])
            plugin.rpc.sendpay(route, payment_hash, label, payment_secret=payment_secret)
            running_for = int(time.time()) - start_ts
            result = plugin.rpc.waitsendpay(payment_hash, max(retry_for - running_for, 0))
            if not result.get('status') == 'complete':
                return False  # should not happen, but maybe API changes
            payload['success_msg'].append(f"{amount + fees}msat sent over {len(route)} "
                                          f"hops to {payload['command']} {amount}msat "
                                          f"[{chunk + 1}/{payload['chunks']}]")
            # we need to wait for HTLC to resolve, so remaining amounts
            # can be calculated correctly for the next chunk
            wait_ours(plugin, payload['scid'], ours)
            return True

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
                excludes.append(f"{erring_channel}/{erring_direction}")


def read_params(command: str, scid: str, percentage: float, chunks: int,
                retry_for: int, maxfeepercent: float, exemptfee: Millisatoshi):

    # check parameters
    if command != 'drain' and command != 'fill' and command != 'setbalance':
        raise RpcError(command, {}, {'message': 'Invalid command. Must be "drain", "fill" or "setbalance"'})
    percentage = float(percentage)
    if percentage < 0 or percentage > 100 or command != 'setbalance' and percentage == 0.0:
        raise RpcError(command, {}, {'message': 'Percentage must be between 0 and 100'})
    if chunks < 0:
        raise RpcError(command, {}, {'message': 'Negative chunks do not make sense. Try a positive '
                                                'value or use 0 (default) for auto-detection.'})

    # forge operation payload
    payload = {
        "command": command,
        "scid": scid,
        "percentage": percentage,
        "chunks": chunks,
        "retry_for": retry_for,
        "maxfeepercent": maxfeepercent,
        "exemptfee": exemptfee,
        "labels": [],
        "success_msg": [],
    }

    # cache some often required data
    payload['my_id'] = plugin.getinfo.get('id')
    payload['start_ts'] = int(time.time())
    payload['mychannels'] = plugin.rpc.listchannels(source=payload['my_id']).get('channels')

    # translate a 'setbalance' into respective drain or fill
    if command == 'setbalance':
        spendable, receivable = spendable_from_scid(payload)
        total = spendable + receivable
        target = Millisatoshi(int(int(total) * (0.01 * payload['percentage'])))
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
    peer_id = peer_from_scid(payload)
    get_channel(payload, peer_id)  # ensures or raises error
    test_or_set_chunks(payload)
    plugin.log("%s  %s  %d%%  %d chunks" % (payload['command'], payload['scid'], payload['percentage'], payload['chunks']))

    # iterate of chunks, default just one
    for chunk in range(payload['chunks']):
        # we discover remaining capacities for each chunk,
        # as fees from previous chunks affect reserves
        spendable, receivable = spendable_from_scid(payload)
        total = spendable + receivable
        amount = Millisatoshi(int(int(total) * (0.01 * payload['percentage'] / payload['chunks'])))
        if amount == Millisatoshi(0):
            raise RpcError(payload['command'], payload, {'message': 'Cannot process chunk. Amount would be 0msat.'})

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
                plugin.log("Trying... chunk:%s/%s  spendable:%s  receivable:%s  htlc_fee:%s =>  amount:%s" % (chunk + 1, payload['chunks'], spendable, receivable, htlc_fee, amount))

                try:
                    result = try_for_htlc_fee(payload, peer_id, amount, chunk, spendable)
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
            return cleanup(payload, e)

    return cleanup(payload)


@plugin.method("drain")
def drain(plugin, scid: str, percentage: float = 100, chunks: int = 0, retry_for: int = 60,
          maxfeepercent: float = 0.5, exemptfee: Millisatoshi = Millisatoshi(5000)):
    """Draining channel liquidity with circular payments.

    Percentage defaults to 100, resulting in an empty channel.
    Chunks defaults to 0 (auto-detect).
    Use 'drain 10' to decrease a channels total balance by 10%.
    """
    payload = read_params('drain', scid, percentage, chunks, retry_for, maxfeepercent, exemptfee)
    return execute(payload)


@plugin.method("fill")
def fill(plugin, scid: str, percentage: float = 100, chunks: int = 0, retry_for: int = 60,
         maxfeepercent: float = 0.5, exemptfee: Millisatoshi = Millisatoshi(5000)):
    """Filling channel liquidity with circular payments.

    Percentage defaults to 100, resulting in a full channel.
    Chunks defaults to 0 (auto-detect).
    Use 'fill 10' to incease a channels total balance by 10%.
    """
    payload = read_params('fill', scid, percentage, chunks, retry_for, maxfeepercent, exemptfee)
    return execute(payload)


@plugin.method("setbalance")
def setbalance(plugin, scid: str, percentage: float = 50, chunks: int = 0, retry_for: int = 60,
               maxfeepercent: float = 0.5, exemptfee: Millisatoshi = Millisatoshi(5000)):
    """Brings a channels own liquidity to X percent using circular payments.

    Percentage defaults to 50, resulting in a balanced channel.
    Chunks defaults to 0 (auto-detect).
    Use 'setbalance 100' to fill a channel. Use 'setbalance 0' to drain a channel.
    """
    payload = read_params('setbalance', scid, percentage, chunks, retry_for, maxfeepercent, exemptfee)
    return execute(payload)


@plugin.init()
def init(options, configuration, plugin):
    rpchelp = plugin.rpc.help().get('help')
    # detect if server cli has moved `listpeers.channels[]` to `listpeerchannels`
    # See https://github.com/ElementsProject/lightning/pull/5825
    # TODO: replace by rpc version check once v23 is released
    plugin.listpeerchannels = False
    if len([c for c in rpchelp if c["command"].startswith("listpeerchannels ")]) != 0:
        plugin.listpeerchannels = True

    # do all the stuff that needs to be done just once ...
    plugin.getinfo = plugin.rpc.getinfo()
    plugin.rpcversion = cln_parse_rpcversion(plugin.getinfo.get('version'))
    plugin.configs = plugin.rpc.listconfigs()
    plugin.cltv_final = plugin.configs.get('cltv-final')

    # use getroute amount_msat/msatoshi field depending on version
    plugin.msatfield = 'amount_msat'
    if plugin.rpcversion[0] == 0 and plugin.rpcversion[1] < 12:
        plugin.msatfield = 'msatoshi'

    plugin.log("Plugin drain.py initialized")


plugin.run()
