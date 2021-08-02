#!/usr/bin/env python3
"""Commando is a plugin to allow one node to control another.  You use
"commando" to send commands, and the 'commando-writer' and
'commando-reader' to allow nodes to send you commands.

The formats are:

type:4C4F - execute this command
type:594B - reply (with more coming)
type:594D - last reply

Each one is an 8 byte id (to link replies to command), followed by JSON.
"""
from pyln.client import Plugin, RpcError
import json
import textwrap
import random

plugin = Plugin()

# "YOLO"!
COMMANDO_CMD = 0x4c4f

# Replies are split across multiple CONTINUES, then TERM.
COMMANDO_REPLY_CONTINUES = 0x594b
COMMANDO_REPLY_TERM = 0x594d


class CommandResponse:
    def __init__(self, req):
        self.buf = bytes()
        self.req = req


def split_cmd(cmdstr):
    """Interprets JSON and method and params"""
    cmd = json.loads(cmdstr)

    return cmd['method'], cmd.get('params')


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


def exec_command(plugin, peer_id, idnum, method, params):
    """Run an arbitrary command and message back the result"""
    try:
        res = {'result': plugin.rpc.call(method, params)}
    except RpcError as e:
        res = {'error': e.error}

    send_result(plugin, peer_id, idnum, res)


def exec_read_command(plugin, peer_id, idnum, method, params):
    """Run a list or get command and message back the result"""
    if method.startswith('list') or method.startswith('get'):
        exec_command(plugin, peer_id, idnum, method, params)
    else:
        send_result(plugin, peer_id, idnum, {'error': "Not permitted"})


@plugin.hook('custommsg')
def on_custommsg(peer_id, payload, plugin, **kwargs):
    pbytes = bytes.fromhex(payload)
    mtype = int.from_bytes(pbytes[:2], "big")
    idnum = int.from_bytes(pbytes[2:10], "big")
    data = pbytes[10:]

    if mtype == COMMANDO_CMD:
        if peer_id in plugin.writers:
            exec_command(plugin, peer_id, idnum, *split_cmd(data))
        elif peer_id in plugin.readers:
            exec_read_command(plugin, peer_id, idnum, *split_cmd(data))
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


@plugin.async_method("commando")
def commando(plugin, request, peer_id, method, params=None):
    """Send a command to node_id, and wait for a response"""
    res = {'method': method}
    if params:
        res['params'] = params

    while True:
        idnum = random.randint(0, 2**64)
        if idnum not in plugin.reqs:
            break

    plugin.reqs[idnum] = CommandResponse(request)
    send_msg(plugin, peer_id, COMMANDO_CMD, idnum, json.dumps(res))


@plugin.init()
def init(options, configuration, plugin):
    plugin.writers = options['commando_writer']
    plugin.readers = options['commando_reader']
    plugin.reqs = {}

    # dev-sendcustommsg was renamed to sendcustommsg for 0.10.1
    try:
        plugin.rpc.help('sendcustommsg')
        plugin.msgcmd = 'sendcustommsg'
    except RpcError:
        plugin.msgcmd = 'dev-sendcustommsg'

    plugin.log("Initialized with readers {}, writers {}"
               .format(plugin.readers, plugin.writers))


plugin.add_option('commando_writer',
                  description="What nodeid can do all commands?",
                  default=[],
                  multi=True)
plugin.add_option('commando_reader',
                  description="What nodeid can do list/get commands?",
                  default=[],
                  multi=True)
plugin.run()
