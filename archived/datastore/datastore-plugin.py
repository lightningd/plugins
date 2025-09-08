#!/usr/bin/env python3
"""This does the actual datastore work, if the main plugin says there's no
datastore support.  We can't even load this if there's real datastore support.
"""

from pyln.client import Plugin, RpcException
from collections import namedtuple
import os
import shelve
from typing import Optional, Sequence, List, Union

# Error codes
DATASTORE_DEL_DOES_NOT_EXIST = 1200
DATASTORE_DEL_WRONG_GENERATION = 1201
DATASTORE_UPDATE_ALREADY_EXISTS = 1202
DATASTORE_UPDATE_DOES_NOT_EXIST = 1203
DATASTORE_UPDATE_WRONG_GENERATION = 1204
DATASTORE_UPDATE_HAS_CHILDREN = 1205
DATASTORE_UPDATE_NO_CHILDREN = 1206

plugin = Plugin()
Entry = namedtuple("Entry", ["generation", "data"])


# A singleton to most commands turns into a [].
def normalize_key(key: Union[Sequence[str], str]) -> List[str]:
    if not isinstance(key, list) and not isinstance(key, tuple):
        key = [key]
    return key


# We turn list into nul-separated hexbytes for storage (shelve needs all keys to be strings)
def key_to_hex(key: Sequence[str]) -> str:
    return b"\0".join([bytes(k, encoding="utf8") for k in key]).hex()


def hex_to_key(hexstr: str) -> List[str]:
    return [b.decode() for b in bytes.fromhex(hexstr).split(b"\0")]


def datastore_entry(key: Sequence[str], entry: Optional[Entry]):
    """Return a dict representing the entry"""

    if isinstance(key, str):
        key = [key]

    ret = {"key": key}

    if entry is not None:
        # Entry may be a simple tuple; convert
        entry = Entry(*entry)
        ret["generation"] = entry.generation
        ret["hex"] = entry.data.hex()

        # FFS, Python3 seems happy with \0 in UTF-8.
        if 0 not in entry.data:
            try:
                ret["string"] = entry.data.decode("utf8")
            except UnicodeDecodeError:
                pass
    return ret


@plugin.method("datastore")
def datastore(plugin, key, string=None, hex=None, mode="must-create", generation=None):
    """Add/modify a {key} and {hex}/{string} data to the data store,
    optionally insisting it be {generation}"""

    key = normalize_key(key)
    khex = key_to_hex(key)
    if string is not None:
        if hex is not None:
            raise RpcException("Cannot specify both string and hex")
        data = bytes(string, encoding="utf8")
    elif hex is None:
        raise RpcException("Must specify string or hex")
    else:
        data = bytes.fromhex(hex)

    if mode == "must-create":
        if khex in plugin.datastore:
            raise RpcException("already exists", DATASTORE_UPDATE_ALREADY_EXISTS)
    elif mode == "must-replace":
        if khex not in plugin.datastore:
            raise RpcException("does not exist", DATASTORE_UPDATE_DOES_NOT_EXIST)
    elif mode == "create-or-replace":
        if generation is not None:
            raise RpcException("generation only valid with" " must-create/must-replace")
        pass
    elif mode == "must-append":
        if generation is not None:
            raise RpcException("generation only valid with" " must-create/must-replace")
        if khex not in plugin.datastore:
            raise RpcException("does not exist", DATASTORE_UPDATE_DOES_NOT_EXIST)
        data = plugin.datastore[khex].data + data
    elif mode == "create-or-append":
        if generation is not None:
            raise RpcException("generation only valid with" " must-create/must-replace")
        data = plugin.datastore.get(khex, Entry(0, bytes())).data + data
    else:
        raise RpcException("invalid mode")

    # Make sure parent doesn't exist
    parent = [key[0]]
    for i in range(1, len(key)):
        if key_to_hex(parent) in plugin.datastore:
            raise RpcException(
                "Parent key [{}] exists".format(",".join(parent)),
                DATASTORE_UPDATE_NO_CHILDREN,
            )
        parent += [key[i]]

    if khex in plugin.datastore:
        entry = plugin.datastore[khex]
        if generation is not None:
            if entry.generation != generation:
                raise RpcException(
                    "generation is different", DATASTORE_UPDATE_WRONG_GENERATION
                )
        gen = entry.generation + 1
    else:
        # Make sure child doesn't exist (grossly inefficient)
        if any([hex_to_key(k)[: len(key)] == key for k in plugin.datastore]):
            raise RpcException("Key has children", DATASTORE_UPDATE_HAS_CHILDREN)
        gen = 0

    plugin.datastore[khex] = Entry(gen, data)
    return datastore_entry(key, plugin.datastore[khex])


@plugin.method("deldatastore")
def deldatastore(plugin, key, generation=None):
    """Remove a {key} from the data store"""

    key = normalize_key(key)
    khex = key_to_hex(key)

    if khex not in plugin.datastore:
        raise RpcException("does not exist", DATASTORE_DEL_DOES_NOT_EXIST)

    entry = plugin.datastore[khex]
    if generation is not None and entry.generation != generation:
        raise RpcException("generation is different", DATASTORE_DEL_WRONG_GENERATION)

    ret = datastore_entry(key, entry)
    del plugin.datastore[khex]
    return ret


@plugin.method("listdatastore")
def listdatastore(plugin, key=[]):
    """List datastore entries"""

    key = normalize_key(key)
    ret = []
    prev = None
    for khex, e in sorted(plugin.datastore.items()):
        k = hex_to_key(khex)
        if k[: len(key)] != key:
            continue

        # Don't print sub-children
        if len(k) > len(key) + 1:
            if prev is None or k[: len(key) + 1] != prev:
                prev = k[: len(key) + 1]
                ret += [datastore_entry(prev, None)]
        else:
            ret += [datastore_entry(k, e)]

    return {"datastore": ret}


def upgrade_store(plugin):
    """Initial version of this plugin had no generation numbers"""
    try:
        oldstore = shelve.open("datastore.dat", "r")
    except:
        return
    plugin.log("Upgrading store to have generation numbers", level="unusual")
    datastore = shelve.open("datastore_v1.dat", "c")
    for k, d in oldstore.items():
        datastore[key_to_hex([k])] = Entry(0, d)
    oldstore.close()
    datastore.close()
    os.unlink("datastore.dat")


@plugin.init()
def init(options, configuration, plugin):
    upgrade_store(plugin)
    plugin.datastore = shelve.open("datastore_v1.dat")


plugin.run()
