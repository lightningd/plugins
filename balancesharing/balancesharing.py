#!/usr/bin/env python3
"""

"""

import pyln.client
import json

plugin = pyln.client.Plugin()

# __version__ was introduced in 0.0.7.1, with utf8 passthrough support.
try:
    if version.parse(lightning.__version__) >= version.parse("0.0.7.1"):
        have_utf8 = True
except Exception:
    pass


@plugin.method("foafbalance")
def foafbalance(plugin):
    """gets the balance of our friends channels"""
    reply = {}
    info = plugin.rpc.getinfo()
    #addr = plugin.rpc.dev_rescan_outputs()
    msg = r'ff' * 32
    #serialized = r'04070020' + msg
    for peer in plugin.rpc.listpeers()["peers"]:
        res = plugin.rpc.dev_sendcustommsg(peer["id"], msg)
        plugin.log(str(res))
    nid = info["id"]
    reply["id"] = nid
    #reply["addr"] = addr
    reply["change"] = nid
    return reply


@plugin.hook('peer_connected')
def on_connected(plugin, **kwargs):
    plugin.log("GOT PEER CONNECTION HOOK")
    return {'result': 'continue'}


@plugin.hook('custommsg')
def on_custommsg(peer_id, message, plugin, **kwargs):
    plugin.log("Got a custom message {msg} from peer {peer_id}".format(
        msg=message,
        peer_id=peer_id
    ))
    return {'result': 'continue'}


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("Plugin balancesharing.py initialized")


plugin.run()
