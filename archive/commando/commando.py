#!/usr/bin/env python3
"""Commando is a plugin to allow one node to control another.  You use
"commando" to send commands, with 'method', 'params' and optional
'rune' which authorizes it.

Additionally, you can use "commando-rune" to create/add restrictions to
existing runes (you can also use the runes.py library).

Rather than handing a rune every time, peers can do "commando-cacherune"
to make it the persistent default for their peer_id.

The formats are:

type:4C4D - execute this command (with more coming)
type:4C4F - execute this command
type:594B - reply (with more coming)
type:594D - last reply

Each one is an 8 byte id (to link replies to command), followed by JSON.

"""
from pyln.client import Plugin, RpcError  # type: ignore
import json
import textwrap
import time
import random
import secrets
import string
import runes  # type: ignore
import multiprocessing
from typing import Dict, Tuple, Optional

plugin = Plugin()

# "YOLO"!
COMMANDO_CMD_CONTINUES = 0x4c4d
COMMANDO_CMD_TERM = 0x4c4f

# Replies are split across multiple CONTINUES, then TERM.
COMMANDO_REPLY_CONTINUES = 0x594b
COMMANDO_REPLY_TERM = 0x594d


class CommandResponse:
    def __init__(self, req):
        self.buf = bytes()
        self.req = req


class InReq:
    def __init__(self, idnum):
        self.idnum = idnum
        self.buf = b''
        self.discard = False

    def append(self, data):
        if not self.discard:
            self.buf += data

    def start_discard(self):
        self.buf = b''
        self.discard = True


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


def send_msgs(plugin, peer_id, idnum, obj, msgtype_cont, msgtype_term):
    # We can only send 64k in a message, but there is 10 byte overhead
    # in the message header; 65000 is safe.
    parts = textwrap.wrap(json.dumps(obj), 65000)
    for p in parts[:-1]:
        send_msg(plugin, peer_id, msgtype_cont, idnum, p)

    send_msg(plugin, peer_id, msgtype_term, idnum, parts[-1])


def send_result(plugin, peer_id, idnum, res):
    send_msgs(plugin, peer_id, idnum, res,
              COMMANDO_REPLY_CONTINUES, COMMANDO_REPLY_TERM)


def send_request(plugin, peer_id, idnum, req):
    send_msgs(plugin, peer_id, idnum, req,
              COMMANDO_CMD_CONTINUES, COMMANDO_CMD_TERM)


def is_rune_valid(plugin, runestr) -> Tuple[Optional[runes.Rune], str]:
    """Is this runestring valid, and authorized for us?"""
    try:
        rune = runes.Rune.from_base64(runestr)
    except:  # noqa: E722
        return None, 'Malformed base64 string'

    if not plugin.masterrune.is_rune_authorized(rune):
        return None, 'Invalid rune string'

    return rune, ''


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


def command_run(plugin, peer_id, idnum, method, params):
    """Function to run a command and write the result"""
    try:
        res = {'result': plugin.rpc.call(method, params)}
    except RpcError as e:
        res = {'error': e.error}
    send_result(plugin, peer_id, idnum, res)


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
            # But commando-rune is useful, so hardcode that.
            if method == "commando-rune":
                if isinstance(params, list):
                    res = {'result': commando_rune(plugin, *params)}
                else:
                    res = {'result': commando_rune(plugin, **params)}
            else:
                res = {'error': 'FIXME: Refusing to call inside ourselves'}
        else:
            # The subprocess does send_result itself: pyln-client doesn't
            # support async RPC yet.
            multiprocessing.Process(target=command_run,
                                    args=(plugin, peer_id, idnum, method, params)).start()
            return

    send_result(plugin, peer_id, idnum, res)


@plugin.async_hook('custommsg')
def on_custommsg(peer_id, payload, plugin, request, **kwargs):
    pbytes = bytes.fromhex(payload)
    mtype = int.from_bytes(pbytes[:2], "big")
    idnum = int.from_bytes(pbytes[2:10], "big")
    data = pbytes[10:]

    if mtype == COMMANDO_CMD_CONTINUES:
        if peer_id not in plugin.in_reqs or idnum != plugin.in_reqs[peer_id].idnum:
            plugin.in_reqs[peer_id] = InReq(idnum)
        plugin.in_reqs[peer_id].append(data)

        # If you have cached a rune, give 10MB, otherwise 1MB.
        # We can have hundreds of these things...
        max_cmdlen = 1000000
        if peer_id in plugin.peer_runes:
            max_cmdlen *= 10

        if len(plugin.in_reqs[peer_id].buf) > max_cmdlen:
            plugin.in_reqs[peer_id].start_discard()
    elif mtype == COMMANDO_CMD_TERM:
        # Prepend any prior data from COMMANDO_CMD_CONTINUES:
        if peer_id in plugin.in_reqs:
            data = plugin.in_reqs[peer_id].buf + data
            discard = plugin.in_reqs[peer_id].discard
            del plugin.in_reqs[peer_id]
            # Were we ignoring this for being too long?  Error out now.
            if discard:
                send_result(plugin, peer_id, idnum,
                            {'error': "Command too long"})
                request.set_result({'result': 'continue'})
                return

        method, params, runestr = split_cmd(data)
        try_command(plugin, peer_id, idnum, method, params, runestr)
    elif mtype == COMMANDO_REPLY_CONTINUES:
        if idnum in plugin.out_reqs:
            plugin.out_reqs[idnum].buf += data
    elif mtype == COMMANDO_REPLY_TERM:
        if idnum in plugin.out_reqs:
            plugin.out_reqs[idnum].buf += data
            finished = plugin.out_reqs[idnum]
            del plugin.out_reqs[idnum]

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
    request.set_result({'result': 'continue'})


@plugin.subscribe('disconnect')
def on_disconnect(id, plugin, request, **kwargs):
    if id in plugin.in_reqs:
        del plugin.in_reqs[id]


@plugin.async_method("commando")
def commando(plugin, request, peer_id, method, params=None, rune=None):
    """Send a command to node_id, and wait for a response"""
    res = {'method': method}
    if params:
        res['params'] = params
    if rune:
        res['rune'] = rune

    while True:
        idnum = random.randint(0, 2**64)
        if idnum not in plugin.out_reqs:
            break

    plugin.out_reqs[idnum] = CommandResponse(request)
    send_request(plugin, peer_id, idnum, res)


@plugin.method("commando-cacherune")
def commando_cacherune(plugin, rune):
    """Sets the rune given to the persistent rune for this peer_id"""
    # This is intercepted by commando runner, above.
    raise RpcError('commando-cacherune', {},
                   'Must be called as a remote commando call')


def add_reader_restrictions(rune: runes.Rune) -> str:
    """Let them execute list or get, but not getsharesecret!"""
    # Allow list*, get* or summary.
    rune.add_restriction(runes.Restriction.from_str('method^list'
                                                    '|method^get'
                                                    '|method=summary'))
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


@plugin.method("commando-rune")
def commando_rune(plugin, rune=None, restrictions=[]):
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
    elif isinstance(restrictions, str):
        this_rune.add_restriction(runes.Restriction.from_str(restrictions))
    else:
        for r in restrictions:
            this_rune.add_restriction(runes.Restriction.from_str(r))

    # Now we've succeeded, update rune_counter.
    if rune is None:
        plugin.rpc.datastore(key=['commando', 'rune_counter'],
                             string=str(plugin.rune_counter + 1),
                             mode='must-replace',
                             generation=plugin.rune_counter_generation)
        plugin.rune_counter += 1
        plugin.rune_counter_generation += 1

    return {'rune': this_rune.to_base64()}


@plugin.init()
def init(options, configuration, plugin):
    plugin.out_reqs = {}
    plugin.in_reqs = {}
    plugin.writers = options['commando-writer']
    plugin.readers = options['commando-reader']
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


plugin.add_option('commando-writer',
                  description="What nodeid can do all commands?",
                  default=[],
                  multi=True)
plugin.add_option('commando-reader',
                  description="What nodeid can do list/get/summary commands?",
                  default=[],
                  multi=True)
plugin.run()
