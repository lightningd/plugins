#!/usr/bin/env python3
"""Plugin that refuses all HTLCs."""
from pyln.client import Plugin

plugin = Plugin()


@plugin.hook("htlc_accepted")
def on_htlc_accepted(htlc, onion, plugin, **kwargs):
    return {'result': 'fail', 'failure_message': '2002'}


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("refuse_htlcs.py initializing")


plugin.run()
