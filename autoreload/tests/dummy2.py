#!/usr/bin/env python3

from pyln.client import Plugin

plugin = Plugin()

@plugin.method('dummy')
def on_dummy():
    pass

plugin.run()
