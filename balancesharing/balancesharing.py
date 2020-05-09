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
    nid = info["id"]
    reply["id"] = nid
    return reply


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("Plugin balancesharing.py initialized")


plugin.run()
