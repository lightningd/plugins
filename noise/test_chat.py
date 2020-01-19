from pyln.testing.fixtures import *
from pyln.testing.utils import wait_for
from pprint import pprint
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
    assert(m2['verified'] == True)


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

    msg = l4.rpc.recvmsg(last_id=-1)


def test_zbase32():
    zb32 = b'd75qtmgijm79rpooshmgzjwji9gj7dsdat8remuskyjp9oq1ugkaoj6orbxzhuo4njtyh96e3aq84p1tiuz77nchgxa1s4ka4carnbiy'
    b = zbase32.decode(zb32)
    enc = zbase32.encode(b)
    assert(enc == zb32)
