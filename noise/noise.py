#!/usr/bin/env python3
from pyln.client import Plugin, RpcError
from pyln.proto.primitives import varint_decode, varint_encode
from onion import TlvPayload
from binascii import hexlify, unhexlify
import struct
import string
import random
from io import BytesIO
import logging
from collections import namedtuple
import shelve
from pyln.proto.onion import OnionPayload
import zbase32
import hashlib
import os

plugin = Plugin()

TLV_KEYSEND_PREIMAGE = 34349341
TLV_NOISE_MESSAGE = 34349334
TLV_NOISE_SIGNATURE = 34349335

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
            "payment": self.payment,
            "verified": self.verified,
        }


def serialize_payload(n, blockheight):
    block, tx, out = n['channel'].split('x')
    payload = hexlify(struct.pack(
        "!cQQL", b'\x00',
        int(block) << 40 | int(tx) << 16 | int(out),
        int(n['amount_msat']),
        blockheight + n['delay'])).decode('ASCII')
    payload += "00" * 12
    return payload


def buildpath(plugin, node_id, payload, amt, exclusions):
    blockheight = plugin.rpc.getinfo()['blockheight']
    route = plugin.rpc.getroute(node_id, amt, 10, exclude=exclusions)['route']
    first_hop = route[0]
    # Need to shift the parameters by one hop
    hops = []
    for h, n in zip(route[:-1], route[1:]):
        # We tell the node h about the parameters to use for n (a.k.a. h + 1)
        hops.append({
            "type": "legacy",
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
                return {'route': route, 'payment_hash': payment_hash, 'attempt': attempt+1}

            plugin.log("Retrying delivery.")

            # TODO Store the failing channel in the exclusions
    raise ValueError('Could not reach destination {node_id}'.format(node_id=node_id))


@plugin.async_method('sendmsg')
def sendmsg(node_id, msg, plugin, request, pay=None, **kwargs):
    payload = TlvPayload()
    payload.add_field(TLV_NOISE_MESSAGE, msg.encode('UTF-8'))


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
    sigcheck = plugin.rpc.checkmessage(sigmsg, sig['zbase'])
    sig = zbase32.decode(sig['zbase'])
    payload.add_field(TLV_NOISE_SIGNATURE, sig)

    res = deliver(
        node_id,
        payload.to_bytes(),
        amt=pay if pay is not None else 10,
        payment_hash=payment_hash
    )
    request.set_result(res)


@plugin.async_method('recvmsg')
def recvmsg(plugin, request, last_id=None, **kwargs):
    next_id = int(last_id) + 1 if last_id is not None else len(plugin.messages)
    if next_id < len(plugin.messages):
        request.set_result(plugin.messages[int(last_id)].to_dict())
    else:
        plugin.receive_waiters.append(request)


@plugin.hook('htlc_accepted')
def on_htlc_accepted(onion, htlc, plugin, **kwargs):
    payload = OnionPayload.from_hex(onion['payload'])

    msg = Message(
        id=len(plugin.messages),
        sender=None,
        body=payload.get(34349334).value,
        signature=payload.get(34349335).value,
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
        res = {
            'result': 'resolve',
            'payment_key': hexlify(preimage.value).decode('ASCII')
        }
    else:
        res = {'result': 'continue'}

    plugin.messages.append(msg)
    for r in plugin.receive_waiters:
        r.set_result(msg.to_dict())
    plugin.receive_waiters = []

    return res


@plugin.init()
def init(configuration, options, plugin, **kwargs):
    print("Starting noise chat plugin")
    plugin.messages = []
    plugin.receive_waiters = []

plugin.run()
