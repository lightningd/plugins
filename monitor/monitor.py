#!/usr/bin/env python3
"""
This is a quick hack and adapted plugin from the summary.py plugin (orinigally written by Rusty Russell
This one is adapted by Rene Pickhardt and aims to help you identify inactive channels quickly
"""

from packaging import version
import pyln.client
import json

plugin = pyln.client.Plugin()

# __version__ was introduced in 0.0.7.1, with utf8 passthrough support.
try:
    if version.parse(lightning.__version__) >= version.parse("0.0.7.1"):  # noqa F821
        have_utf8 = True
except Exception:
    pass


@plugin.method("monitor")
def monitor(plugin):
    """Monitors channels of this node."""
    reply = {}
    reply["num_connected"] = 0
    reply["num_channels"] = 0
    reply["format-hint"] = "simple"
    peers = plugin.rpc.listpeers()
    info = plugin.rpc.getinfo()
    nid = info["id"]
    chans = {}
    states = {}
    for p in peers["peers"]:
        channels = []
        if "channels" in p:
            channels = p["channels"]
        elif "num_channels" in p and p["num_channels"] > 0:
            channels = plugin.rpc.listpeerchannels(p["id"])["channels"]
        for c in channels:
            if p["connected"]:
                reply["num_connected"] += 1
            reply["num_channels"] += 1
            state = c["state"]
            if state in states:
                states[state] += 1
            else:
                states[state] = 1
            connected = "connected" if p["connected"] else "disconnected"
            fees = "unknown onchain fees"
            funding = c.get("funding_msat", None)
            if funding is not None:
                our_funding = funding[nid]
                their_funding = funding[p["id"]]
                if int(our_funding) == 0:
                    fees = "their onchain fees"
                elif int(their_funding) == 0:
                    fees = "our onchain fees"
                else:
                    fees = "shared onchain fees"
            total = int(c["total_msat"])
            ours = int(c["our_reserve_msat"]) + int(c["spendable_msat"])
            our_fraction = "{:4.2f}% owned by us".format(ours * 100 / total)
            tmp = "\t".join(
                [
                    p["id"],
                    connected,
                    fees,
                    our_fraction,
                    c["short_channel_id"]
                    if "short_channel_id" in c
                    else "unknown scid",
                ]
            )
            if state in chans:
                chans[state].append(tmp)
            else:
                chans[state] = [tmp]
    reply["states"] = []
    for key, value in states.items():
        reply["states"].append(key + ": " + str(value))
    reply["channels"] = json.dumps(chans)
    return reply


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("Plugin monitor.py initialized")


plugin.run()
