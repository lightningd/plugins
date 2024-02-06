#!/usr/bin/env python3
"""Plugin that holds on to HTLCs for 5 seconds, then reject them."""
from pyln.client import Plugin
import time

plugin = Plugin()


@plugin.hook("htlc_accepted")
def on_htlc_accepted(htlc, onion, plugin, **kwargs):
    time.sleep(5)
    return {'result': 'fail', 'failure_message': '2002'}


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("hold_htlcs.py initializing")


plugin.run()
