import os
from pyln.testing.fixtures import *  # type: ignore
from pyln.client import RpcError  # type: ignore
import pytest
import json
import runes  # type: ignore
import commando
import time

plugin_path = os.path.join(os.path.dirname(__file__), "commando.py")
datastore_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                              "datastore", "datastore.py")


def test_add_reader_restrictions():
    mrune = runes.MasterRune(bytes(32))
    runestr = commando.add_reader_restrictions(mrune.copy())
    assert mrune.check_with_reason(runestr, {'method': 'listfoo'}) == (True, '')
    assert mrune.check_with_reason(runestr, {'method': 'getfoo'}) == (True, '')
    assert mrune.check_with_reason(runestr, {'method': 'getsharedsecret'}) == (False, 'method: = getsharedsecret')
    assert mrune.check_with_reason(runestr, {'method': 'summary'}) == (True, '')
    assert mrune.check_with_reason(runestr, {'method': 'fail'}) == (False, 'method: does not start with list AND method: does not start with get AND method: != summary')


def test_commando(node_factory):
    l1, l2 = node_factory.line_graph(2, fundchannel=True)

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
    with pytest.raises(RpcError, match='method: does not start with list AND method: does not start with get AND method: != summary'):
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


def test_commando_rune(node_factory):
    l1, l2, l3 = node_factory.line_graph(3, fundchannel=False,
                                         opts={'plugin': [plugin_path,
                                                          datastore_path]})

    l1.daemon.logsearch_start = 0
    l1.daemon.wait_for_log("Initialized with rune support")
    l2.daemon.logsearch_start = 0
    l2.daemon.wait_for_log("Initialized with rune support")
    l3.daemon.logsearch_start = 0
    l3.daemon.wait_for_log("Initialized with rune support")

    wrune = l2.rpc.commando_rune()['rune']
    rrune = l2.rpc.commando_rune(restrictions='readonly')['rune']

    # This works
    res = l1.rpc.call(method='commando',
                      payload={'peer_id': l2.info['id'],
                               'rune': rrune,
                               'method': 'listpeers'})
    assert len(res['peers']) == 2

    # This fails (no rune!)
    with pytest.raises(RpcError, match='Not authorized'):
        l1.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'method': 'withdraw'})

    # This fails (ro rune!)
    with pytest.raises(RpcError, match='Not authorized'):
        res = l1.rpc.call(method='commando',
                          payload={'peer_id': l2.info['id'],
                                   'rune': rrune,
                                   'method': 'withdraw'})

    # This would succeed, except missing param)
    with pytest.raises(RpcError, match='missing required parameter'):
        res = l1.rpc.call(method='commando',
                          payload={'peer_id': l2.info['id'],
                                   'rune': wrune,
                                   'method': 'withdraw'})

    # We can subrune and use that rune explicitly.
    lcrune = l2.rpc.commando_rune(rrune, 'method=listchannels')['rune']
    with pytest.raises(RpcError, match='Not authorized'):
        l1.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'rune': lcrune,
                             'method': 'listpeers'})

    l1.rpc.call(method='commando',
                payload={'peer_id': l2.info['id'],
                         'rune': lcrune,
                         'method': 'listchannels'})

    # Only allow it to list l3's channels (by source, second param)
    lcrune = l2.rpc.commando_rune(rrune, ['method=listchannels',
                                          'pnamesource=' + l3.info['id']
                                          + '|' + 'parr1=' + l3.info['id']])['rune']

    # Needs rune!
    with pytest.raises(RpcError, match='Not authorized'):
        l3.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'method': 'listchannels',
                             'params': [None, l3.info['id']]})
    # Command wrong
    with pytest.raises(RpcError, match='Not authorized.*method'):
        l3.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'rune': lcrune,
                             'method': 'withdraw'})

    # Params missing
    with pytest.raises(RpcError, match='Not authorized.*missing'):
        l3.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'rune': lcrune,
                             'method': 'listchannels'})

    # Param wrong (array)
    with pytest.raises(RpcError, match='Not authorized.*parr1'):
        l3.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'rune': lcrune,
                             'method': 'listchannels',
                             'params': [None, l2.info['id']]})

    # Param wrong (obj)
    with pytest.raises(RpcError, match='Not authorized.*pnamesource'):
        l3.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'rune': lcrune,
                             'method': 'listchannels',
                             'params': {'source': l2.info['id']}})

    # Param right (array)
    l3.rpc.call(method='commando',
                payload={'peer_id': l2.info['id'],
                         'rune': lcrune,
                         'method': 'listchannels',
                         'params': [None, l3.info['id']]})

    # Param right (obj)
    l3.rpc.call(method='commando',
                payload={'peer_id': l2.info['id'],
                         'rune': lcrune,
                         'method': 'listchannels',
                         'params': {'source': l3.info['id']}})


def test_commando_cacherune(node_factory):
    l1, l2 = node_factory.line_graph(2, fundchannel=False,
                                     opts={'plugin': [plugin_path,
                                                      datastore_path]})
    restrictions = ['method=listchannels',
                    'pnamesource={id}|parr1={id}'.format(id=l1.info['id'])]
    lcrune = l2.rpc.commando_rune(restrictions=restrictions)['rune']

    # You can't set it, it needs to be via commando!
    with pytest.raises(RpcError,
                       match='Must be called as a remote commando call'):
        l1.rpc.commando_cacherune(lcrune)

    l1.rpc.commando(peer_id=l2.info['id'],
                    method='commando-cacherune',
                    rune=lcrune)

    # Param wrong (array)
    with pytest.raises(RpcError, match='Not authorized.*parr1'):
        l1.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'method': 'listchannels',
                             'params': [None, l2.info['id']]})

    # Param wrong (obj)
    with pytest.raises(RpcError, match='Not authorized.*pnamesource'):
        l1.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'method': 'listchannels',
                             'params': {'source': l2.info['id']}})

    # Param right (array)
    l1.rpc.call(method='commando',
                payload={'peer_id': l2.info['id'],
                         'method': 'listchannels',
                         'params': [None, l1.info['id']]})

    # Param right (obj)
    l1.rpc.call(method='commando',
                payload={'peer_id': l2.info['id'],
                         'method': 'listchannels',
                         'params': {'source': l1.info['id']}})

    # Still works after restart!
    l2.restart()
    l1.rpc.connect(l2.info['id'], 'localhost', l2.port)
    l1.rpc.call(method='commando',
                payload={'peer_id': l2.info['id'],
                         'method': 'listchannels',
                         'params': {'source': l1.info['id']}})


def test_rune_time(node_factory):
    l1, l2 = node_factory.line_graph(2, fundchannel=False,
                                     opts={'plugin': [plugin_path,
                                                      datastore_path]})

    rune = l1.rpc.commando_rune(restrictions=["method=commando-rune",
                                              "pnamerestrictions^id=|parr1^id=",
                                              "time<{}"
                                              .format(int(time.time()) + 15)])['rune']
    # l2 has to obey restrictions
    with pytest.raises(RpcError, match='Not authorized.*pnamerestrictions'):
        l2.rpc.commando(peer_id=l1.info['id'], method='commando-rune', rune=rune)

    with pytest.raises(RpcError, match='Not authorized.*pnamerestrictions'):
        l2.rpc.commando(peer_id=l1.info['id'], method='commando-rune', rune=rune,
                        params={'restrictions': 'id<{}'.format(l2.info['id'])})

    # By name
    rune2 = l2.rpc.commando(peer_id=l1.info['id'],
                            method='commando-rune',
                            rune=rune,
                            params={'restrictions': 'id={}'.format(l2.info['id'])})
    # By position
    rune2a = l2.rpc.commando(peer_id=l1.info['id'],
                             method='commando-rune',
                             rune=rune,
                             params=[None, 'id={}'.format(l2.info['id'])])
    # r2a ID will be 1 greater than r2 ID
    r2 = runes.Rune.from_base64(rune2['rune'])
    r2a = runes.Rune.from_base64(rune2a['rune'])
    assert len(r2.restrictions) == len(r2a.restrictions)
    assert r2a.restrictions[0].alternatives == [runes.Alternative(r2.restrictions[0].alternatives[0].field,
                                                                  r2.restrictions[0].alternatives[0].cond,
                                                                  str(int(r2.restrictions[0].alternatives[0].value) + 1))]
    for r2_r, r2a_r in zip(r2.restrictions[1:], r2a.restrictions[1:]):
        assert r2_r == r2a_r

    time.sleep(16)
    with pytest.raises(RpcError, match='Not authorized.*time'):
        l2.rpc.commando(peer_id=l1.info['id'],
                        method='commando-rune',
                        rune=rune,
                        params={'restrictions': 'id={}'.format(l2.info['id'])})


def test_readonly(node_factory):
    l1, l2 = node_factory.line_graph(2, fundchannel=False,
                                     opts={'plugin': [plugin_path,
                                                      datastore_path]})
    rrune = l2.rpc.commando_rune(restrictions='readonly')['rune']

    l1.rpc.call(method='commando',
                payload={'peer_id': l2.info['id'],
                         'method': 'listchannels',
                         'rune': rrune,
                         'params': {'source': l1.info['id']}})

    with pytest.raises(RpcError, match='Not authorized.* = getsharedsecret'):
        l1.rpc.commando(peer_id=l2.info['id'],
                        rune=rrune,
                        method='getsharedsecret')

    with pytest.raises(RpcError, match='Not authorized.* = listdatastore'):
        l1.rpc.commando(peer_id=l2.info['id'],
                        rune=rrune,
                        method='listdatastore')


def test_megacmd(node_factory):
    l1, l2 = node_factory.line_graph(2, fundchannel=False,
                                     opts={'plugin': [plugin_path,
                                                      datastore_path]})
    rrune = l2.rpc.commando_rune(restrictions='readonly')['rune']

    # Proof that it got the rune: fails with "Unknown command" not "Not authorized"
    with pytest.raises(RpcError, match='Unknown command'):
        l1.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'method': 'get' + 'x' * 130000,
                             'rune': rrune,
                             'params': {}})

    with pytest.raises(RpcError, match='Command too long'):
        l1.rpc.call(method='commando',
                    payload={'peer_id': l2.info['id'],
                             'method': 'get' + 'x' * 1100000,
                             'rune': rrune,
                             'params': {}})
