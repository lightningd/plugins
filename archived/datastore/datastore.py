#!/usr/bin/env python3
from pyln.client import Plugin, RpcError
import shelve
import os


plugin = Plugin()


def unload_store(plugin):
    """When we have a real store, we transfer our contents into it"""
    try:
        datastore = shelve.open("datastore_v1.dat", "r")
    except:
        return

    plugin.log(
        "Emptying store into main store (resetting generations!)", level="unusual"
    )
    for k, (g, data) in datastore.items():
        try:
            plugin.rpc.datastore(key=[k], hex=data.hex())
        except RpcError as e:
            plugin.log("Failed to put {} into store: {}".format(k, e), level="broken")
    datastore.close()
    plugin.log("Erasing our store", level="unusual")
    os.unlink("datastore_v1.dat")


@plugin.init()
def init(options, configuration, plugin):
    # If we have real datastore commands, don't load plugin.
    try:
        plugin.rpc.help("datastore")
        unload_store(plugin)
        return {"disable": "there is a real datastore command"}
    except RpcError:
        pass

    # Start up real plugin now
    plugin.rpc.plugin_start(
        os.path.join(os.path.dirname(__file__), "datastore-plugin.py")
    )
    return {"disable": "no builtin-datastore: plugin loaded"}


plugin.run()
