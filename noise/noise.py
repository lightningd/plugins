#!/usr/bin/env python3
from binascii import hexlify
from onion import OnionPayload
from onion import TlvPayload
from pyln.client import Plugin, RpcError
import hashlib
import os
import struct
import time
import zbase32


plugin = Plugin()

TLV_KEYSEND_PREIMAGE = 5482373484
TLV_NOISE_MESSAGE = 34349334
TLV_NOISE_SIGNATURE = 34349335
TLV_NOISE_TIMESTAMP = 34349343


class Message(object):
    def __init__(self, sender, body, signature, payment=None, id=None):
        self.id = id
        self.sender = sender
        self.body = body
        self.signature = signature
        self.payment = payment
        self.verified = None

    def to_dict(self):
        return {
            "id": self.id,
            "sender": self.sender,
            "body": self.body,
            "signature": hexlify(self.signature).decode('ASCII'),
            "payment": self.payment.to_dict() if self.payment is not None else None,
            "verified": self.verified,
        }


class Payment(object):
    def __init__(self, payment_key, amount):
        self.payment_key = payment_key
        self.amount = amount

    def to_dict(self):
        return {
            "payment_key": hexlify(self.payment_key).decode('ASCII'),
            "payment_hash": hashlib.sha256(self.payment_key).hexdigest(),
            "amount": self.amount,
        }


def serialize_payload(n, blockheight):
    block, tx, out = n['channel'].split('x')
    scid = int(block) << 40 | int(tx) << 16 | int(out)

    def minint(i):
        if i < 2**8:
            return struct.pack("!B", i)
        elif i < 2**16:
            return struct.pack('!H', i)
        elif i < 2**32:
            return struct.pack("!I", i)
        else:
            return struct.pack("!Q", i)

    amt = int(n['amount_msat'])
    cltv = blockheight + n['delay']

    payload = TlvPayload()
    payload.add_field(2, minint(amt))
    payload.add_field(4, minint(cltv))
    payload.add_field(6, minint(scid))
    return payload.to_bytes().hex()


def buildpath(plugin, node_id, payload, amt, exclusions):
    blockheight = plugin.rpc.getinfo()['blockheight']
    route = plugin.rpc.getroute(node_id, amt, 10, exclude=exclusions)['route']
    first_hop = route[0]
    # Need to shift the parameters by one hop
    hops = []
    for h, n in zip(route[:-1], route[1:]):
        # We tell the node h about the parameters to use for n (a.k.a. h + 1)
        hops.append({
            "type": "tlv",
            "pubkey": h['id'],
            "payload": serialize_payload(n, blockheight)
        })

    # The last hop has a special payload:
    hops.append({
        "type": "tlv",
        "pubkey": route[-1]['id'],
        "payload": hexlify(payload).decode('ASCII'),
    })
    return first_hop, hops, route


def deliver(node_id, payload, amt, payment_hash, max_attempts=5):
    """Do your best to deliver `payload` to `node_id`.
    """
    exclusions = []
    payment_hash = hexlify(payment_hash).decode('ASCII')

    for attempt in range(max_attempts):
        plugin.log("Starting attempt {} to deliver message to {}".format(attempt, node_id))

        first_hop, hops, route = buildpath(plugin, node_id, payload, amt, exclusions)
        onion = plugin.rpc.createonion(hops=hops, assocdata=payment_hash)

        plugin.rpc.sendonion(onion=onion['onion'],
                             first_hop=first_hop,
                             payment_hash=payment_hash,
                             shared_secrets=onion['shared_secrets']
                             )
        try:
            plugin.rpc.waitsendpay(payment_hash=payment_hash)
            return {'route': route, 'payment_hash': payment_hash, 'attempt': attempt}
        except RpcError as e:
            failcode = e.error['data']['failcode']
            failingidx = e.error['data']['erring_index']
            if failcode == 16399 or failingidx == len(hops):
                return {'route': route, 'payment_hash': payment_hash, 'attempt': attempt + 1}

            plugin.log("Retrying delivery.")

            # TODO Store the failing channel in the exclusions
    raise ValueError('Could not reach destination {node_id}'.format(node_id=node_id))


@plugin.async_method('sendmsg')
def sendmsg(node_id, msg, plugin, request, pay=None, **kwargs):
    """Sends a chat message.

    First paramter is the message payload as a string.
    """
    timestamp = struct.pack("!Q", int(time.time() * 1000))
    payload = TlvPayload()
    payload.add_field(TLV_NOISE_MESSAGE, msg.encode('UTF-8'))
    payload.add_field(TLV_NOISE_TIMESTAMP, timestamp)

    payment_key = os.urandom(32)
    payment_hash = hashlib.sha256(payment_key).digest()

    # If we don't want to tell the recipient how to claim the funds unset the
    # payment_key
    if pay is not None:
        payload.add_field(TLV_KEYSEND_PREIMAGE, payment_key)

    # Signature generation always has to be last, otherwise we won't agree on
    # the TLV payload and verification ends up with a bogus sender node_id.
    sigmsg = hexlify(payload.to_bytes()).decode('ASCII')
    sig = plugin.rpc.signmessage(sigmsg)
    plugin.rpc.checkmessage(sigmsg, sig['zbase'])
    sig = zbase32.decode(sig['zbase'])
    payload.add_field(TLV_NOISE_SIGNATURE, sig)

    res = deliver(
        node_id,
        payload.to_bytes(),
        amt=pay if pay is not None else 10,
        payment_hash=payment_hash
    )
    request.set_result(res)


@plugin.async_method('allmsgs')
def allmsgs(plugin, request, **kwargs):
    """
    Prints all messages that have been received
    """
    msg_list = {}
    for i in range(len(plugin.messages)):
        res = plugin.messages[int(i)].to_dict()
        res['total_messages'] = len(plugin.messages)
        msg_list["message"+str(i)] = res
    request.set_result(msg_list)


@plugin.async_method('recvmsg')
def recvmsg(plugin, request, msg_id=None, **kwargs):
    """Receives a chat message.

    Returns a `concurrent.futures.Future`.
    Optional parameter `msg_id` can be supplied to return an older messages.
    """
    msg_id = int(msg_id) if msg_id is not None else len(plugin.messages)
    if msg_id < len(plugin.messages):
        res = plugin.messages[msg_id].to_dict()
        res['total_messages'] = len(plugin.messages)
        request.set_result(res)
    else:
        plugin.receive_waiters.append(request)


@plugin.hook('htlc_accepted')
def on_htlc_accepted(onion, htlc, plugin, **kwargs):
    payload = OnionPayload.from_hex(onion['payload'])
    if not isinstance(payload, TlvPayload):
        plugin.log("Payload is not a TLV payload")
        return {'result': 'continue'}

    body_field = payload.get(34349334)
    signature_field = payload.get(34349335)

    if body_field is None or signature_field is None:
        plugin.log("Missing message body or signature, ignoring HTLC")
        return {'result': 'continue'}

    msg = Message(
        id=len(plugin.messages),
        sender=None,
        body=body_field.value,
        signature=signature_field.value,
        payment=None)

    # Filter out the signature so we can check it against the rest of the payload
    sigpayload = TlvPayload()
    sigpayload.fields = filter(lambda x: x.typenum != TLV_NOISE_SIGNATURE, payload.fields)
    sigmsg = hexlify(sigpayload.to_bytes()).decode('ASCII')

    zsig = zbase32.encode(msg.signature).decode('ASCII')
    sigcheck = plugin.rpc.checkmessage(sigmsg, zsig)
    msg.sender = sigcheck['pubkey']
    msg.verified = sigcheck['verified']

    preimage = payload.get(TLV_KEYSEND_PREIMAGE)
    if preimage is not None:
        msg.payment = Payment(preimage.value, htlc['amount_msat'])
        res = {
            'result': 'resolve',
            'payment_key': hexlify(preimage.value).decode('ASCII')
        }
    else:
        res = {'result': 'continue'}

    plugin.messages.append(msg)
    for r in plugin.receive_waiters:
        m = msg.to_dict()
        m['total_messages'] = len(plugin.messages)
        r.set_result(m)
    plugin.receive_waiters = []

    return res


@plugin.init()
def init(configuration, options, plugin, **kwargs):
    print("Starting noise chat plugin")
    plugin.messages = []
    plugin.receive_waiters = []


plugin.run()
