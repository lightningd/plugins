#!/usr/bin/env python3
import os
import struct
from binascii import hexlify, unhexlify
from collections import namedtuple
from decimal import Decimal
from threading import Timer

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, hmac
from pyln.client import Millisatoshi, Plugin, RpcError
from pyln.proto.invoice import (
    Invoice, RouteHint, RouteHintSet, bech32_encode, bitarray_to_u5, bitstring,
    coincurve, encode_fallback, hashlib, shorten_amount, tagged, tagged_bytes)
from pyln.proto.onion import RoutingOnion, chacha20_stream, ecdh, TlvPayload
from pyln.proto.primitives import PrivateKey, Secret

# Something we don't have a preimage for, and allows downstream nodes
# to recognize this as a test payment.
PAYMENT_HASH = b"AA" * 32

# The private key used for the final hop. Well-known so the
# penultimate hop can decode the onion.
PRIVKEY = PrivateKey(b"\xAA" * 32)
PUBKEY = PRIVKEY.public_key()

plugin = Plugin()

KeySet = namedtuple("KeySet", ["rho", "mu", "um", "pad", "gamma", "pi", "ammag"])


def generate_key(secret: bytes, prefix: bytes):
    h = hmac.HMAC(prefix, hashes.SHA256(), backend=default_backend())
    h.update(secret)
    return h.finalize()


def generate_keyset(secret: Secret) -> KeySet:
    types = [bytes(f, "ascii") for f in KeySet._fields]
    keys = [generate_key(secret.data, t) for t in types]
    return KeySet(*keys)


class MyInvoice(Invoice):
    def __init__(self, *args, **kwargs):
        Invoice.__init__(self, *args, **kwargs)
        self.features = 0

    def encode(self, privkey):
        if self.amount:
            amount = Decimal(str(self.amount))
            # We can only send down to millisatoshi.
            if amount * 10 ** 12 % 10:
                raise ValueError(
                    "Cannot encode {}: too many decimal places".format(self.amount)
                )

            amount = self.currency + shorten_amount(amount)
        else:
            amount = self.currency if self.currency else ""

        hrp = "ln" + amount

        # Start with the timestamp
        data = bitstring.pack("uint:35", self.date)

        # Payment hash
        data += tagged_bytes("p", self.paymenthash)
        tags_set = set()

        if self.route_hints is not None:
            for rh in self.route_hints.route_hints:
                data += tagged_bytes("r", rh.to_bytes())

        if self.features != 0:
            b = "{:x}".format(self.features)
            if len(b) % 2 == 1:
                b = "0" + b
            data += tagged_bytes("9", unhexlify(b))

        for k, v in self.tags:

            # BOLT #11:
            #
            # A writer MUST NOT include more than one `d`, `h`, `n` or `x` fields,
            if k in ("d", "h", "n", "x"):
                if k in tags_set:
                    raise ValueError("Duplicate '{}' tag".format(k))

            if k == "r":
                pubkey, channel, fee, cltv = v
                route = (
                    bitstring.BitArray(pubkey)
                    + bitstring.BitArray(channel)
                    + bitstring.pack("intbe:64", fee)
                    + bitstring.pack("intbe:16", cltv)
                )
                data += tagged("r", route)
            elif k == "f":
                data += encode_fallback(v, self.currency)
            elif k == "d":
                data += tagged_bytes("d", v.encode())
            elif k == "s":
                data += tagged_bytes("s", v)
            elif k == "x":
                # Get minimal length by trimming leading 5 bits at a time.
                expirybits = bitstring.pack("intbe:64", v)[4:64]
                while expirybits.startswith("0b00000"):
                    expirybits = expirybits[5:]
                data += tagged("x", expirybits)
            elif k == "h":
                data += tagged_bytes("h", hashlib.sha256(v.encode("utf-8")).digest())
            elif k == "n":
                data += tagged_bytes("n", v)
            else:
                # FIXME: Support unknown tags?
                raise ValueError("Unknown tag {}".format(k))

            tags_set.add(k)

        # BOLT #11:
        #
        # A writer MUST include either a `d` or `h` field, and MUST NOT include
        # both.
        if "d" in tags_set and "h" in tags_set:
            raise ValueError("Cannot include both 'd' and 'h'")
        if "d" not in tags_set and "h" not in tags_set:
            raise ValueError("Must include either 'd' or 'h'")

        # We actually sign the hrp, then data (padded to 8 bits with zeroes).
        privkey = coincurve.PrivateKey(secret=bytes(unhexlify(privkey)))
        data += privkey.sign_recoverable(
            bytearray([ord(c) for c in hrp]) + data.tobytes()
        )

        return bech32_encode(hrp, bitarray_to_u5(data))


@plugin.method("testinvoice")
def testinvoice(destination, amount=None, **kwargs):
    if amount is not None:
        amount = Millisatoshi(amount).to_btc()

    network = plugin.rpc.listconfigs()['network']

    currency = {
        'bitcoin': 'bc',
        'regtest': 'bcrt',
        'signet': 'tb',
        'testnet': 'tb',
        'liquid-regtest': 'ert',
        'liquid': 'ex',
    }[network]

    inv = MyInvoice(
        paymenthash=unhexlify(PAYMENT_HASH),
        amount=amount,
        currency=currency,
    )
    inv.pubkey = PUBKEY
    inv.tags.append(
        ("d", "Test invoice for {destination}".format(destination=destination))
    )

    # Payment_secret
    inv.tags.append(("s", os.urandom(32)))

    # The real magic is here: we add a routehint that tells the sender
    # how to get to this non-existent node. The trick is that it has
    # to go through the real destination.

    rh = RouteHint()
    rh.pubkey = unhexlify(destination)
    rh.short_channel_id = 1 << 40 | 1 << 16 | 1
    rh.fee_base_msat = 1
    rh.fee_proportional_millionths = 1
    rh.cltv_expiry_delta = 9
    rhs = RouteHintSet()
    rhs.add(rh)
    inv.route_hints = rhs

    inv.features |= 1 << 14  # payment secret
    inv.features |= 1 << 16  # basic_mpp
    inv.features |= 1 << 8  # TLV payloads

    return {
        "invoice": inv.encode(PRIVKEY.serializeCompressed().hex()),
        "attention": "The invoice is destined for {}, but forced through {} which will process it instead. So don't worry if decoding the invoice returns a different destination than you'd expect.".format(
            PUBKEY.serializeCompressed().hex(), destination
        ),
    }


def wrap_error(keys, err):
    b = unhexlify(err)
    c = len(b)
    padlen = 256 - c
    pad = b"\x00" * padlen
    b = struct.pack("!H", c) + b + struct.pack("!H", padlen) + pad
    assert len(b) == 256 + 2 + 2
    h = hmac.HMAC(keys.um, hashes.SHA256(), backend=default_backend())
    h.update(b)
    # h.update(unhexlify(PAYMENT_HASH))
    hh = h.finalize()
    b = bytearray(hh + b)
    chacha20_stream(keys.ammag, b)
    return hexlify(bytes(b)).decode("ASCII")


@plugin.method("paytest")
def paytest(destination, amount, request, plugin):
    inv = testinvoice(destination, amount)

    try:
        plugin.rpc.pay(inv["invoice"])
        raise ValueError("pay succeeded, this is impossible...")
    except RpcError as e:
        print(e)
        # TODO Reinterpret result as success or failure.

    return {
        "invoice": inv,
        "status": plugin.rpc.paystatus(inv["invoice"])["pay"][0],
    }


def timeout(plugin, secret):
    if secret not in plugin.pending:
        return

    parts = plugin.pending.get(secret, None)

    if parts is None:
        return

    print("Timing out payment with secret={secret}".format(secret=secret))
    for p in parts:
        p[0].set_result({"result": "fail", "failure_onion": wrap_error(p[4], b"0017")})


@plugin.async_hook("htlc_accepted")
def on_htlc_accepted(onion, htlc, request, plugin, *args, **kwargs):
    print(
        "Got an incoming HTLC for {payment_hash}".format(
            payment_hash=htlc["payment_hash"]
        )
    )
    # If this is not a test payment, pass it on
    if 'short_channel_id' not in onion or onion["short_channel_id"] != "1x1x1":
        return request.set_result({"result": "continue"})

    # Decode the onion so we get the details the virtual recipient
    # would get.
    ro = RoutingOnion.from_hex(onion["next_onion"])
    try:
        payload, next_onion = ro.unwrap(PRIVKEY, unhexlify(PAYMENT_HASH))
    except Exception:
        return request.set_result({"result": "continue"})

    if next_onion is not None:
        # Whoops, apparently the virtual node isn't the last hop, fail
        # by default.
        return request.set_result({"result": "continue"})

    # Shared key required for the response
    shared_secret = ecdh(PRIVKEY, ro.ephemeralkey)

    # MPP payments really only work with TlvPayloads, otherwise we
    # don't know the total. In addition the `.get(8)` would fail on a
    # LegacyOnionPayload, so we just tell them to go away here.
    if not isinstance(payload, TlvPayload):
        return {'result': 'continue'}

    # We key the payment by payment_secret rather than payment_hash so
    # we collide less often.
    ps = payload.get(8).value.hex()
    if ps not in plugin.pending:
        plugin.pending[ps] = []
        # Start the timer
        Timer(60.0, timeout, args=(plugin, ps)).start()

    payment_data = payload.get(8).value
    # secret = payment_data[:32]
    total = payment_data[32:].hex()

    total = int(total, 16)
    plugin.pending[ps].append(
        (
            request,
            total,
            int(Millisatoshi(onion["forward_msat"])),
            shared_secret,
            generate_keyset(shared_secret),
        )
    )

    parts = plugin.pending[ps]
    received = sum([p[2] for p in parts])
    print("Received {}/{} with {} parts".format(received, total, len(parts)))

    if received != total:
        return

    for p in parts:
        p[0].set_result(
            {
                "result": "fail",
                "failure_onion": wrap_error(p[4], b"400F"),
            }
        )

    del plugin.pending[ps]


@plugin.init()
def init(plugin, *args, **kwargs):
    # Multi-part payments that are currently pending
    plugin.pending = {}


plugin.run()
