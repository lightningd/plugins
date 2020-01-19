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

plugin = Plugin()


class Message(object):
    def __init__(self, sender, body, signature, payment=None, id=None):
        self.id = id
        self.sender = sender
        self.body = body
        self.signature = signature
        self.payment = payment

    def to_dict(self):
        return {
            "id": self.id,
            "sender": self.sender,
            "body": self.body,
            "signature": hexlify(self.signature).decode('ASCII'),
            "payment": self.payment,
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


def deliver(node_id, payload, amt, max_attempts=5, payment_hash=None):
    """Do your best to deliver `payload` to `node_id`.
    """
    if payment_hash is None:
        payment_hash = ''.join(random.choice(string.hexdigits) for _ in range(64)).lower()

    exclusions = []

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
            print(e)
            failcode = e.error['data']['failcode']
            if failcode == 16399:
                return {'route': route, 'payment_hash': payment_hash, 'attempt': attempt+1}

            plugin.log("Retrying delivery.")

            # TODO Store the failing channel in the exclusions
    raise ValueError('Could not reach destination {node_id}'.format(node_id=node_id))


@plugin.async_method('sendmsg')
def sendmsg(node_id, msg, plugin, request, amt=1000, **kwargs):
    payload = TlvPayload()
    payload.add_field(34349334, msg.encode('UTF-8'))

    # Sign the message:
    sig = plugin.rpc.signmessage(msg)['signature']
    sig = unhexlify(sig)
    payload.add_field(34349336, sig)

    res = deliver(node_id, payload.to_bytes(), amt=amt)
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

    # TODO verify the signature to extract the sender

    msg = Message(
        id=len(plugin.messages),
        sender="AAA",
        body=payload.get(34349334).value,
        signature=payload.get(34349336).value,
        payment=None)

    plugin.messages.append(msg)
    for r in plugin.receive_waiters:
        r.set_result(msg.to_dict())
    plugin.receive_waiters = []

    return {'result': 'continue'}


@plugin.init()
def init(configuration, options, plugin, **kwargs):
    print("Starting noise chat plugin")
    plugin.messages = []
    plugin.receive_waiters = []

plugin.run()
