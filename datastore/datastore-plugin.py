#!/usr/bin/env python3
"""This does the actual datastore work, if the main plugin says there's no
datastore support.  We can't even load this if there's real datastore support.
"""
from pyln.client import Plugin, RpcException
from collections import namedtuple
import os
import shelve

# Error codes
DATASTORE_DEL_DOES_NOT_EXIST = 1200
DATASTORE_DEL_WRONG_GENERATION = 1201
DATASTORE_UPDATE_ALREADY_EXISTS = 1202
DATASTORE_UPDATE_DOES_NOT_EXIST = 1203
DATASTORE_UPDATE_WRONG_GENERATION = 1204

plugin = Plugin()
Entry = namedtuple('Entry', ['generation', 'data'])

def datastore_entry(key, entry: Entry):
    """Return a dict representing the entry"""

    # Entry may be a simple tuple; convert
    entry = Entry(*entry)
    ret = {'key': key, 'generation': entry.generation, 'hex': entry.data.hex()}

    # FFS, Python3 seems happy with \0 in UTF-8.
    if 0 not in entry.data:
        try:
            ret['string'] = entry.data.decode('utf8')
        except UnicodeDecodeError:
            pass
    return ret


@plugin.method("datastore")
def datastore(plugin, key, string=None, hex=None, mode="must-create", generation=None):
    """Add/modify a {key} and {hex}/{string} data to the data store,
optionally insisting it be {generation}"""

    if string is not None:
        if hex is not None:
            raise RpcException("Cannot specify both string or hex")
        data = bytes(string, encoding="utf8")
    elif hex is None:
        raise RpcException("Must specify string or hex")
    else:
        data = bytes.fromhex(hex)

    if mode == "must-create":
        if key in plugin.datastore:
            raise RpcException("already exists", DATASTORE_UPDATE_ALREADY_EXISTS)
    elif mode == "must-replace":
        if key not in plugin.datastore:
            raise RpcException("does not exist", DATASTORE_UPDATE_DOES_NOT_EXIST)
    elif mode == "create-or-replace":
        if generation is not None:
            raise RpcException("generation only valid with"
                               " must-create/must-replace")
        pass
    elif mode == "must-append":
        if generation is not None:
            raise RpcException("generation only valid with"
                               " must-create/must-replace")
        if key not in plugin.datastore:
            raise RpcException("does not exist", DATASTORE_UPDATE_DOES_NOT_EXIST)
        data = plugin.datastore[key].data + data
    elif mode == "create-or-append":
        if generation is not None:
            raise RpcException("generation only valid with"
                               " must-create/must-replace")
        data = plugin.datastore.get(key, Entry(0, bytes())).data + data
    else:
        raise RpcException("invalid mode")

    if key in plugin.datastore:
        entry = plugin.datastore[key]
        if generation is not None:
            if entry.generation != generation:
                raise RpcException("generation is different",
                                   DATASTORE_UPDATE_WRONG_GENERATION)
        gen = entry.generation + 1
    else:
        gen = 0

    plugin.datastore[key] = Entry(gen, data)
    return datastore_entry(key, plugin.datastore[key])


@plugin.method("deldatastore")
def deldatastore(plugin, key, generation=None):
    """Remove a {key} from the data store"""

    if not key in plugin.datastore:
        raise RpcException("does not exist", DATASTORE_DEL_DOES_NOT_EXIST)

    entry = plugin.datastore[key]
    if generation is not None and entry.generation != generation:
        raise RpcException("generation is different",
                           DATASTORE_DEL_WRONG_GENERATION)

    ret = datastore_entry(key, entry)
    del plugin.datastore[key]
    return ret


@plugin.method("listdatastore")
def listdatastore(plugin, key=None):
    """List datastore entries"""
    if key is None:
        return {'datastore': [datastore_entry(k, e)
                              for k, e in plugin.datastore.items()]}
    if key in plugin.datastore:
        return {'datastore': [datastore_entry(key, plugin.datastore[key])]}
    return {'datastore': []}


def upgrade_store(plugin):
    """Initial version of this plugin had no generation numbers"""
    try:
        oldstore = shelve.open('datastore.dat', 'r')
    except:
        return
    plugin.log("Upgrading store to have generation numbers", level='unusual')
    datastore = shelve.open('datastore_v1.dat', 'c')
    for k, d in oldstore.items():
        datastore[k] = Entry(0, d)
    oldstore.close()
    datastore.close()
    os.unlink('datastore.dat')


@plugin.init()
def init(options, configuration, plugin):
    upgrade_store(plugin)
    plugin.datastore = shelve.open('datastore_v1.dat')


plugin.run()
