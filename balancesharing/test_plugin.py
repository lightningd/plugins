from pyln.testing.fixtures import *
import unittest
from pyln.client import RpcError


@unittest.skipIf(not DEVELOPER, "Needs dev-sendcustommsg")
def test_sendcustommsg(node_factory):
    """Check that we can send custommsgs to peers in various states.

    `l2` is the node under test. `l1` has a channel with `l2` and should
    therefore be attached to `channeld`. `l4` is just connected, so it should
    be attached to `openingd`. `l3` has a channel open, but is disconnected
    and we can't send to it.

    """
    plugin = os.path.join(os.path.dirname(__file__), "balancesharing.py")
    opts = {'log-level': 'io', 'plugin': plugin}
    l1, l2, l3 = node_factory.line_graph(3, opts=opts)
    l4 = node_factory.get_node(options=opts)
    l2.connect(l4)
    l3.stop()
    msg = r'ff' * 32
    serialized = r'04070020' + msg

    # This should work since the peer is currently owned by `channeld`
    l2.rpc.dev_sendcustommsg(l1.info['id'], msg)
    l2.daemon.wait_for_log(
        r'{peer_id}-{owner}-chan#[0-9]: \[OUT\] {serialized}'.format(
            owner='channeld', serialized=serialized, peer_id=l1.info['id']
        )
    )
    l1.daemon.wait_for_log(r'\[IN\] {}'.format(serialized))
    l1.daemon.wait_for_log(
        r'Got a custom message {serialized} from peer {peer_id}'.format(
            serialized=serialized, peer_id=l2.info['id']))
