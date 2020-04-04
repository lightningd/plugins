from binascii import hexlify
from flaky import flaky
from onion import TlvPayload
from pprint import pprint
from pyln.client import RpcError
from pyln.testing.fixtures import *
from pyln.testing.utils import wait_for
import hashlib
import os
import pytest
import zbase32


plugin = os.path.join(os.path.dirname(__file__), 'noise.py')


def test_sendmsg_success(node_factory, executor):
    opts = [{'plugin': plugin}, {}, {'plugin': plugin}]
    l1, l2, l3 = node_factory.line_graph(3, wait_for_announce=True, opts=opts)

    recv = executor.submit(l3.rpc.recvmsg)
    l1.rpc.sendmsg(l3.info['id'], "Hello world!")

    # This one is tailing the incoming messages
    m1 = recv.result(10)

    # This one should get the same result:
    m2 = l3.rpc.recvmsg(last_id=-1)
    # They should be the same :-)
    assert(m1 == m2)

    assert(m2['sender'] == l1.info['id'])
    assert(m2['verified'])


@flaky
def test_sendmsg_retry(node_factory, executor):
    opts = [{'plugin': plugin}, {}, {'fee-base': 10000}, {'plugin': plugin}]
    l1, l2, l3, l4 = node_factory.line_graph(4, opts=opts)
    l5 = node_factory.get_node()

    l2.openchannel(l5, 10**6)
    l5.openchannel(l4, 10**6)

    def gossip_synced(nodes):
        for a, b in zip(nodes[:-1], nodes[1:]):
            if a.rpc.listchannels() != b.rpc.listchannels():
                return False
        return True

    wait_for(lambda: gossip_synced([l1, l2, l3, l4, l5]))

    # Now stop l5 so the first attempt will fail.
    l5.stop()

    recv = executor.submit(l4.rpc.recvmsg)

    send = executor.submit(l1.rpc.sendmsg, l4.info['id'], "Hello world!")

    l1.daemon.wait_for_log(r'Retrying delivery')

    sres = send.result(10)
    assert(sres['attempt'] == 2)
    pprint(sres)
    print(recv.result(10))

    l4.rpc.recvmsg(last_id=-1)


def test_zbase32():
    zb32 = b'd75qtmgijm79rpooshmgzjwji9gj7dsdat8remuskyjp9oq1ugkaoj6orbxzhuo4njtyh96e3aq84p1tiuz77nchgxa1s4ka4carnbiy'
    b = zbase32.decode(zb32)
    enc = zbase32.encode(b)
    assert(enc == zb32)


def test_msg_and_keysend(node_factory, executor):
    opts = [{'plugin': plugin}, {}, {'plugin': plugin}]
    l1, l2, l3 = node_factory.line_graph(3, wait_for_announce=True, opts=opts)
    amt = 10000

    # Check that l3 does not have funds initially
    assert(l3.rpc.listpeers()['peers'][0]['channels'][0]['msatoshi_to_us'] == 0)

    l1.rpc.sendmsg(l3.info['id'], "Hello world!", amt)
    m = l3.rpc.recvmsg(last_id=-1)

    assert(m['sender'] == l1.info['id'])
    assert(m['verified'])
    p = m['payment']
    assert(p is not None)
    assert(p['payment_key'] is not None)
    assert(p['amount'] == '10000msat')

    # Check that l3 actually got the funds I sent it
    wait_for(lambda: l3.rpc.listpeers()['peers'][0]['channels'][0]['msatoshi_to_us'] == amt)


def test_forward_ok(node_factory, executor):
    """All nodes run plugin, forwarding node doesn't crash.

    Reproduces the crash mentioned by @darosior in this comment:
    https://github.com/lightningd/plugins/pull/68#issuecomment-577251902

    """
    opts = [{'plugin': plugin}]*3
    l1, l2, l3 = node_factory.line_graph(3, wait_for_announce=True, opts=opts)

    recv = executor.submit(l3.rpc.recvmsg)
    l1.rpc.sendmsg(l3.info['id'], "Hello world!")

    # This one is tailing the incoming messages
    m1 = recv.result(10)

    # This one should get the same result:
    m2 = l3.rpc.recvmsg(last_id=-1)
    # They should be the same :-)
    assert(m1 == m2)

    assert(m2['sender'] == l1.info['id'])
    assert(m2['verified'])


def test_missing_tlv_fields(node_factory):
    """If we're missing a field we should not crash
    """
    opts = [{'plugin': plugin}]*2
    l1, l2 = node_factory.line_graph(2, wait_for_announce=True, opts=opts)
    payment_key = os.urandom(32)
    payment_hash = hashlib.sha256(payment_key).hexdigest()

    route = l1.rpc.getroute(l2.info['id'], 10, 10)['route']

    def send(key, value):
        hops = [{"type": "tlv", "pubkey": l2.info['id'], "payload": None}]

        payload = TlvPayload()
        payload.add_field(key, value)

        hops[0]['payload'] = payload.to_hex()
        onion = l1.rpc.createonion(hops=hops, assocdata=payment_hash)
        l1.rpc.sendonion(
            onion=onion['onion'],
            first_hop=route[0],
            payment_hash=payment_hash,
            shared_secrets=onion['shared_secrets'],
        )
        with pytest.raises(RpcError, match=r'WIRE_INVALID_ONION_PAYLOAD'):
            l1.rpc.waitsendpay(payment_hash)

    send(34349334, b'Message body')
    assert(l2.daemon.wait_for_log(r'Missing message body or signature'))

    send(34349335, b'00'*32)
    assert(l2.daemon.wait_for_log(r'Missing message body or signature'))
