#!/usr/bin/env python3
"""This does the actual datastore work, if the main plugin says there's no
datastore support.  We can't even load this if there's real datastore support.
"""
from pyln.client import Plugin, RpcError
import shelve


plugin = Plugin()


def datastore_entry(key, data):
    """Return a dict representing the entry"""

    ret = {'key': key, 'hex': data.hex()}

    # FFS, Python3 seems happy with \0 in UTF-8.
    if 0 not in data:
        try:
            ret['string'] = data.decode('utf8')
        except UnicodeDecodeError:
            pass
    return ret


@plugin.method("datastore")
def datastore(plugin, key, string=None, hex=None, mode="must-create"):
    """Add a {key} and {hex}/{string} data to the data store"""

    if string is not None:
        if hex is not None:
            raise RpcError("datastore", {'key': key},
                           {'message': "Cannot specify both string or hex"})
        data = bytes(string, encoding="utf8")
    elif hex is None:
        raise RpcError("datastore", {'key': key},
                       {'message': "Must specify string or hex"})
    else:
        data = bytes.fromhex(hex)

    print("key={}, data={}, mode={}".format(key, data, mode))
    if mode == "must-create":
        if key in plugin.datastore:
            raise RpcError("datastore", {'key': key},
                           {'message': "already exists"})
    elif mode == "must-replace":
        if key not in plugin.datastore:
            raise RpcError("datastore", {'key': key},
                           {'message': "does not exist"})
    elif mode == "create-or-replace":
        pass
    elif mode == "must-append":
        if key not in plugin.datastore:
            raise RpcError("datastore", {'key': key},
                           {'message': "does not exist"})
        data = plugin.datastore[key] + data
    elif mode == "create-or-append":
        data = plugin.datastore.get(key, bytes()) + data
    else:
        raise RpcError("datastore", {'key': key}, {'message': "invalid mode"})

    plugin.datastore[key] = data
    return datastore_entry(key, data)


@plugin.method("deldatastore")
def deldatastore(plugin, key):
    """Remove a {key} from the data store"""

    ret = datastore_entry(key, plugin.datastore[key])
    del plugin.datastore[key]
    return ret


@plugin.method("listdatastore")
def listdatastore(plugin, key=None):
    """List datastore entries"""
    if key is None:
        return {'datastore': [datastore_entry(k, d)
                              for k, d in plugin.datastore.items()]}
    if key in plugin.datastore:
        return {'datastore': [datastore_entry(key, plugin.datastore[key])]}
    return {'datastore': []}


@plugin.init()
def init(options, configuration, plugin):
    plugin.datastore = shelve.open('datastore.dat')


plugin.run()
