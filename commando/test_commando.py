import os
from pyln.testing.fixtures import *  # noqa: F401,F403
from pyln.client import Millisatoshi, RpcError

plugin_path = os.path.join(os.path.dirname(__file__), "commando.py")


def test_commando(node_factory):
    l1, l2 = node_factory.line_graph(2, fundchannel=False)

    l1.rpc.plugin_start(plugin_path, commando_reader=l2.info['id'])
    l2.rpc.plugin_start(plugin_path)

    # This works
    res = l2.rpc.call(method='commando',
                      payload={'peer_id': l1.info['id'],
                               'method': 'listpeers'})
    assert len(res['peers']) == 1
    assert res['peers'][0]['id'] == l2.info['id']

    res = l2.rpc.call(method='commando',
                      payload={'peer_id': l1.info['id'],
                               'method': 'listpeers',
                               'params': {'id': l2.info['id']}})
    assert len(res['peers']) == 1
    assert res['peers'][0]['id'] == l2.info['id']

    # This fails
    with pytest.raises(RpcError, match='Not permitted'):
        l2.rpc.call(method='commando',
                    payload={'peer_id': l1.info['id'],
                             'method': 'withdraw'})

    # As a writer, anything goes.
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path, commando_writer=l2.info['id'])

    with pytest.raises(RpcError, match='missing required parameter'):
        l2.rpc.call(method='commando',
                    payload={'peer_id': l1.info['id'],
                             'method': 'withdraw'})

    ret = l2.rpc.call(method='commando',
                      payload={'peer_id': l1.info['id'],
                               'method': 'ping',
                               'params': {'id': l2.info['id']}})
    assert 'totlen' in ret

    # Now, this will go over a single message!
    ret = l2.rpc.call(method='commando',
                      payload={'peer_id': l1.info['id'],
                               'method': 'getlog',
                               'params': {'level': 'io'}})

    assert len(json.dumps(ret)) > 65535
