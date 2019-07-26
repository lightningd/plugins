#!/usr/bin/env python3
"""

This is a quick hack and adopted plugin from the summary.py plugin (orinigally written by Rusty Russell

This one is adapted by Rene Pickhardt and aimed to help you identify inactive channels quickly

"""

from lightning import Plugin, Millisatoshi
import lightning
import json

plugin = Plugin(autopatch=True)

# __version__ was introduced in 0.0.7.1, with utf8 passthrough support.
try:
    if version.parse(lightning.__version__) >= version.parse("0.0.7.1"):
        have_utf8 = True
except Exception:
    pass

@plugin.method("monitor")
def monitor(plugin):
    """Monitors channels of this node."""

    reply = {}
    reply['num_connected'] = 0
    reply['num_channels'] = 0
    peers = plugin.rpc.listpeers()
    info = plugin.rpc.getinfo()
    nid = info["id"]
    chans={}
    states={}
    for p in peers['peers']:
        for c in p['channels']:
            if p['connected']:
                reply['num_connected'] += 1
            reply['num_channels'] += 1
            state = c['state']
            if state in states:
                states[state]+=1
            else:
                states[state]=1
            connected = "connected"
            if p['connected'] != True:
                connected = "disconnected"
            funding = c['funding_allocation_msat']
            our_funding = funding[nid]
            fees = "our fees"
            if int(our_funding) == 0:
                fees = "their fees"


            total = float(c['msatoshi_total'])
            ours = float(c['our_channel_reserve_satoshis']) + float(c['spendable_msatoshi'])
            our_fraction = "{:4.2f}% owned by us".format(ours*100/total)
            tmp = "\t".join([p['id'], connected, fees, our_fraction, c['short_channel_id']])
            
            if state in chans:
                chans[state].append(tmp)
            else:
                chans[state] = [tmp]

    serialized_states = []
    for key, value in states.items():
        serialized_states.append(key + ": " + str(value))
    reply['states']=serialized_states
    reply['channels'] = chans#json.dumps(chans)
    reply = json.dumps(reply, indent=4)
    return reply


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("Plugin monitor.py initialized")

plugin.run()
