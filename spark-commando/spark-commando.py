#! /usr/bin/python3
from pyln.client import Plugin, RpcError
import runes
import json
import textwrap
import time
import secrets
import string
import pyqrcode
from typing import Dict, Tuple, Optional


plugin = Plugin()

COMMANDO_CMD = 0x4c4f

# Replies are split across multiple CONTINUES, then TERM.
COMMANDO_REPLY_CONTINUES = 0x594b
COMMANDO_REPLY_TERM = 0x594d


def add_reader_restrictions(rune: runes.Rune) -> str:
    """Let them execute list or get, but not getsharesecret!"""
    # Allow spark-list* spark-get*.
    rune.add_restriction(runes.Restriction.from_str('method^spark-list'
                                                    '|method^spark-get'))
    # But not getsharesecret!
    rune.add_restriction(runes.Restriction.from_str('method/getsharedsecret'))
    # And not listdatastore!
    rune.add_restriction(runes.Restriction.from_str('method/listdatastore'))
    return rune.to_base64()


def save_peer_rune(plugin, peer_id, runestr) -> None:
    assert plugin.have_datastore
    plugin.rpc.datastore(key=['commando', 'peer_runes', peer_id],
                         string=runestr,
                         mode='create-or-replace')


def load_peer_runes(plugin) -> Dict[str, str]:
    if not plugin.have_datastore:
        return {}

    peer_runes = {}
    entries = plugin.rpc.listdatastore(key=['commando', 'peer_runes'])
    for entry in entries['datastore']:
        peer_runes[entry['key'][2]] = entry['string']
    return peer_runes



def split_cmd(cmdstr):
    """Interprets JSON and method and params"""
    cmd = json.loads(cmdstr)

    return cmd['method'], cmd.get('params', {}), cmd.get('rune')


def send_msg(plugin, peer_id, msgtype, idnum, contents):
    """Messages are form [8-byte-id][data]"""
    msg = (msgtype.to_bytes(2, 'big')
           + idnum.to_bytes(8, 'big')
           + bytes(contents, encoding='utf8'))
    plugin.rpc.call(plugin.msgcmd, {'node_id': peer_id, 'msg': msg.hex()})


def send_result(plugin, peer_id, idnum, res):
    # We can only send 64k in a message, but there is 10 byte overhead
    # in the message header; 65000 is safe.
    parts = textwrap.wrap(json.dumps(res), 65000)
    for p in parts[:-1]:
        send_msg(plugin, peer_id, COMMANDO_REPLY_CONTINUES, idnum, p)

    send_msg(plugin, peer_id, COMMANDO_REPLY_TERM, idnum, parts[-1])


def is_rune_valid(plugin, runestr) -> Tuple[Optional[runes.Rune], str]:
    """Is this runestring valid, and authorized for us?"""
    try:
        rune = runes.Rune.from_base64(runestr)
    except:  # noqa: E722
        return None, 'Malformed base64 string'

    if not plugin.masterrune.is_rune_authorized(rune):
        return None, 'Invalid rune string'

    return rune, ''


def do_cacherune(plugin, peer_id, runestr):
    if not plugin.have_datastore:
        return {'error': 'No datastore available: try datastore.py?'}

    if runestr is None:
        return {'error': 'No rune set?'}

    rune, whynot = is_rune_valid(plugin, runestr)
    if not rune:
        return {'error': whynot}

    plugin.peer_runes[peer_id] = runestr
    save_peer_rune(plugin, peer_id, runestr)
    return {'result': {'rune': runestr}}

def check_rune(plugin, node_id, runestr, command, params) -> Tuple[bool, str]:
    """If we have a runestr, check it's valid and conditions met"""
    # If they don't specify a rune, we use any previous for this peer
    if runestr is None:
        runestr = plugin.peer_runes.get(node_id)
    if runestr is None:
        # Finally, try reader-writer lists
        if node_id in plugin.writers:
            runestr = plugin.masterrune.to_base64()
        elif node_id in plugin.readers:
            runestr = add_reader_restrictions(plugin.masterrune.copy())

    if runestr is None:
        return False, 'No rune'

    commando_dict = {'time': int(time.time()),
                     'id': node_id,
                     'version': plugin.version,
                     'method': command}

    # FIXME: This doesn't work well with complex params (it makes them str())
    if isinstance(params, list):
        for i, p in enumerate(params):
            commando_dict['parr{}'.format(i)] = p
    else:
        for k, v in params.items():
            # Cannot have punctuation in fieldnames, so remove.
            for c in string.punctuation:
                k = k.replace(c, '')
            commando_dict['pname{}'.format(k)] = v

    return plugin.masterrune.check_with_reason(runestr, commando_dict)

def try_command(plugin, peer_id, idnum, method, params, runestr):
    """Run an arbitrary command and message back the result"""
    # You can always set your rune, even if *that rune* wouldn't
    # allow it!
    if method == 'commando-cacherune':
        res = do_cacherune(plugin, peer_id, runestr)
    else:
        ok, failstr = check_rune(plugin, peer_id, runestr, method, params)
        if not ok:
            res = {'error': 'Not authorized: ' + failstr}
        elif method in plugin.methods:
            # Don't try to call indirectly into ourselves; we deadlock!
            # But enable-spark is useful, so hardcode that.
            if method == "enable-spark":
                if isinstance(params, list):
                    res = {'result': enable_spark(plugin, *params)}
                else:
                    res = {'result': enable_spark(plugin, **params)}
            else:
                res = {'error': 'FIXME: Refusing to call inside ourselves'}
        else:
            try:
                res = {'result': plugin.rpc.call(method, params)}
            except RpcError as e:
                res = {'error': e.error}

    send_result(plugin, peer_id, idnum, res)



@plugin.hook('custommsg')
def on_custommsg(peer_id, payload, plugin, **kwargs):
    pbytes = bytes.fromhex(payload)
    mtype = int.from_bytes(pbytes[:2], "big")
    idnum = int.from_bytes(pbytes[2:10], "big")
    data = pbytes[10:]

    if mtype == COMMANDO_CMD:
        method, params, runestr = split_cmd(data)
        try_command(plugin, peer_id, idnum, method, params, runestr)
    elif mtype == COMMANDO_REPLY_CONTINUES:
        if idnum in plugin.reqs:
            plugin.reqs[idnum].buf += data
    elif mtype == COMMANDO_REPLY_TERM:
        if idnum in plugin.reqs:
            plugin.reqs[idnum].buf += data
            finished = plugin.reqs[idnum]
            del plugin.reqs[idnum]

            try:
                ret = json.loads(finished.buf.decode())
            except Exception as e:
                # Bad response
                finished.req.set_exception(e)
                return {'result': 'continue'}

            if 'error' in ret:
                # Pass through error
                finished.req.set_exception(RpcError('commando', {},
                                                    ret['error']))
            else:
                # Pass through result
                finished.req.set_result(ret['result'])
    return {'result': 'continue'}

def getChannel(peerid, chanid):
    peer = plugin.rpc.listpeers(peerid)
    assert peer, "cannot find peer"

    chan = peer["channels"]
    assert chan["channel_id"]==chanid, "cannot find channel"

    return {peer, chan}



@plugin.method("enable-spark")
def enable_spark(plugin, rune=None, restrictions=[]):
    """Create a rune, (or derive from {rune}) with the given
{restrictions} array (or string), or 'readonly'"""
    if not plugin.have_datastore:
        raise RpcError('commando-rune', {},
                       'No datastore available: try datastore.py?')
    if rune is None:
        this_rune = plugin.masterrune.copy()
        this_rune.add_restriction(runes.Restriction.unique_id(plugin.rune_counter))
    else:
        this_rune, whynot = is_rune_valid(plugin, rune)
        if this_rune is None:
            raise RpcError('commando-rune', {'rune': rune}, whynot)



    if restrictions == 'readonly':
        add_reader_restrictions(this_rune)
    else:
        this_rune.add_restriction(runes.Restriction.from_str("method^spark"))

    # Now we've succeeded, update rune_counter.
    if rune is None:
        plugin.rpc.datastore(key=['commando', 'rune_counter'],
                             string=str(plugin.rune_counter + 1),
                             mode='must-replace',
                             generation=plugin.rune_counter_generation)
        plugin.rune_counter += 1                
        plugin.rune_counter_generation += 1
    
    #Should replace +=1 to +=2?
    res = {}
    res["node_id"] = plugin.rpc.getinfo()["id"]
    res["rune"] = this_rune.to_base64()
    qr = pyqrcode.create(str(res), encoding="ascii")
    qr.show()
    return "Scan the QR and have fun!"


@plugin.method("spark-listpays")
def spark_listpays():
    plugin.log("listpays")
    return plugin.rpc.listpays()

@plugin.method("spark-listpeers")
def spark_listpeers():
    plugin.log("listpeers")
    return plugin.rpc.listpeers()

@plugin.method("spark-getinfo")
def spark_getinfo():
    plugin.log("getinfo")
    return plugin.rpc.getinfo()

@plugin.method("spark-offer")
def spark_offer(amount, discription):
    plugin.log("offer")
    return plugin.rpc.offer(amount, discription)

@plugin.method("spark-listfunds")
def spark_listfunds():
    plugin.log("listfunds")
    return plugin.rpc.listfunds()

@plugin.method("spark-invoice")
def spark_invoice(amt, label, disc):
    plugin.log("invoice")
    return plugin.rpc.invoice(amt, label, disc)

@plugin.method("spark-newaddr")
def spark_invoice():
    plugin.log("newaddr")
    return plugin.rpc.newaddr()

@plugin.method("spark-getlog")
def spark_invoice():
    plugin.log("getlog")
    return plugin.rpc.getlog()

@plugin.method("spark-listconfigs")
def spark_listconfigs():
    plugin.log("listconfigs")
    return plugin.rpc.listconfigs()

@plugin.method("spark-listinvoices")
def spark_listconfigs(plugin):
    """This is the documentation string for the hello-function.

    It gets reported as the description when registering the function
    as a method with `lightningd`.

    If this returns (a dict), that's the JSON "result" returned.  If
    it raises an exception, that causes a JSON "error" return (raising
    pyln.client.RpcException allows finer control over the return).
    """
    plugin.log("listinvoices")
    temp = plugin.rpc.listinvoices()["invoices"]
    res = []
    for i in temp:
        if i["status"]=="paid":
            res.append(i)
    return res


@plugin.method("spark-decodecheck")
def spark_decodecheck(paystr):
    plugin.log("decodecheck")
    s = plugin.rpc.decode(paystr)
    if(s["type"]=="bolt12 offer"):
        assert "recurrence" in s.keys(), "Offers with recurrence are unsupported"
        assert s["quantity_min"] == None or s["msatoshi"] or s["amount"], 'Offers with quantity but no payment amount are unsupported'
        assert not s["send_invoice"] or s["msatoshi"], "send_invoice offers with no amount are unsupported"
        assert not s["send_invoice"] or s["min_quantity"] == None, 'send_invoice offers with quantity are unsupported'
    return s

@plugin.method("spark-connectfund")
def spark_connectfund(peeruri, satoshi, feerate):
        peerid = peeruri.split('@')[0]
        plugin.rpc.connect(peerid)
        res = plugin.rpc.fundchannel(peerid, satoshi, feerate)
        assert (res and res["channel_id"]), "cannot open channel"
        return getChannel(peerid, res["channel_id"])

plugin.method("spark-close")
def spark_close(peerid, chainid, force, timeout):
        res = plugin.rpc.close(peerid, timeout)
        assert res and res["txid"], "Cannot close channel"

        peer,chan = getChannel(peerid, res["channel_id"])
        return {peer, chan, res}

@plugin.init()
def init(options, configuration, plugin):
    plugin.reqs = {}
    plugin.writers = options['admin_writer']
    plugin.readers = options['admin_reader']
    plugin.version = plugin.rpc.getinfo()['version']

    # dev-sendcustommsg was renamed to sendcustommsg for 0.10.1
    try:
        plugin.rpc.help('sendcustommsg')
        plugin.msgcmd = 'sendcustommsg'
    except RpcError:
        plugin.msgcmd = 'dev-sendcustommsg'

    # Unfortunately, on startup it can take a while for
    # the datastore to be loaded (as it's actually a second plugin,
    # loaded by the first.
    end = time.time() + 10
    secret = None
    while time.time() < end:
        try:
            secret = plugin.rpc.listdatastore(['commando', 'secret'])['datastore']
        except RpcError:
            time.sleep(1)
        else:
            break

    if secret is None:
        # Use a throwaway secret
        secret = secrets.token_bytes()
        plugin.have_datastore = False
        plugin.peer_runes = {}
        plugin.log("Initialized without rune support"
                   " (needs datastore.py plugin)",
                   level="info")
    else:
        plugin.have_datastore = True
        if secret == []:
            plugin.log("Creating initial rune secret", level='unusual')
            secret = secrets.token_bytes()
            plugin.rpc.datastore(key=['commando', 'secret'], hex=secret.hex())
            plugin.rune_counter = 0
            plugin.rune_counter_generation = 0
            plugin.rpc.datastore(key=['commando', 'rune_counter'], string=str(0))
        else:
            secret = bytes.fromhex(secret[0]['hex'])
            counter = plugin.rpc.listdatastore(['commando', 'rune_counter'])['datastore'][0]
            plugin.rune_counter = int(counter['string'])
            plugin.rune_counter_generation = int(counter['generation'])
        plugin.log("Initialized with rune support: {} runes so far".format(plugin.rune_counter),
                   level="info")

    plugin.masterrune = runes.MasterRune(secret)
    plugin.peer_runes = load_peer_runes(plugin)


plugin.add_option('admin_writer',
                  description="What nodeid can do all commands?",
                  default=[],
                  multi=True)
plugin.add_option('admin_reader',
                  description="What nodeid can do list/get/summary commands?",
                  default=[],
                  multi=True)

plugin.run()