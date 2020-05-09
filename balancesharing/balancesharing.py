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


# TODO: implement
def has_feature(feature):
    """"check if XXX feature bit present"""
    return True


def get_funds(plugin):
    """"get output and channels"""
    # TODO: switch to real data
    # fund_list = plugin.rpc.listfunds()
    fund_list = list_funds_mock()
    outputs = fund_list["outputs"]
    channels = fund_list["channels"]

    return outputs, channels


def list_funds_mock():
    """"read funds from file"""
    # TODO: add dir
    with open('<dir>/funds.json', 'r') as funds_file:
        data = funds_file.read()

    return json.loads(data)


# TODO: we need to extend this, if we want to handle multiple channels per peer
def get_channel(channels, peer_id):
    """"searches for ONE channel with the given  peer_id"""
    for ch in channels:
        if ch["peer_id"] == peer_id:
            return ch

    return None


@plugin.method("foafbalance")
def foafbalance(plugin):
    """gets the balance of our friends channels"""
    flow_value = 1
    amt_to_rebalance = 10
    reply = {}
    info = plugin.rpc.getinfo()
    msg = r'105b126182746121'

    outputs, channels = get_funds(plugin)

    for peer in plugin.rpc.listpeers()["peers"]:
        # check if peer is the desired state
        if not peer["connected"] or not has_feature(peer["features"]):
            continue
        peer_id = peer["id"]

        res = plugin.rpc.dev_sendcustommsg(peer_id, msg)
        plugin.log("RPC response" + str(res))

    nid = info["id"]
    reply["id"] = nid
    reply["change"] = nid
    return reply


def get_message_type(message):
    assert len(message) > 4
    return message[:4]


def get_message_payload(message):
    assert len(message) > 4
    return message[4:]


def handle_query_foaf_balances(payload, plugin):
    plugin.rpc.listfunds()["channels"]
    return


def send_reply_foaf_balances(peer, channels, plugin):
    # TODO: CHECK if 107b is the correct little endian of 439
    plugin.rpc.dev_sendcustommsg(peer, "107b123412341234")
    return


@plugin.hook('peer_connected')
def on_connected(plugin, **kwargs):
    plugin.log("GOT PEER CONNECTION HOOK")
    return {'result': 'continue'}


@plugin.hook('custommsg')
def on_custommsg(peer_id, message, plugin, **kwargs):
    plugin.log("Got a custom message {msg} from peer {peer_id}".format(
        msg=message,
        peer_id=peer_id
    ))
    # message has to be at least 6 bytes. 4 bytes prefix and 2 bytes for the type
    assert len(message) > 12
    # remove prefix:
    message = message[8:]
    message_type = get_message_type(message)
    message_payload = get_message_payload(message)

    # query_foaf_balances message has type 437 which is 01b5 in hex
    if message_type == "105b":
        plugin.log("received query_foaf_balances message")
        result = handle_query_foaf_balances(message_payload, plugin)
        send_reply_foaf_balances(peer_id, result, plugin)

    plugin.log(message)
    plugin.log(str(type(message)))
    return {'result': 'continue'}


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("Plugin balancesharing.py initialized")


plugin.run()
