#!/usr/bin/env python3
"""
author: Rene Pickhardt (rene.m.pickhardt@ntnu.no) & Michael Ziegler (michael.h.ziegler@ntnu.no)
Date: 9.5.2020
License: MIT
This code computes an optimal split of a payment amount for the use of AMP.
The split is optimal in the sense that it reduces the imbalance of the funds of the node.
More theory about imbalances and the algorithm to decrease the imblance of a node was
suggested by this research: https://arxiv.org/abs/1912.09555
"""

import networkx as nx
import pyln.client
import json
import os
import struct
from binascii import hexlify, unhexlify

QUERY_FOAF_BALANCES = 437
REPLY_FOAF_BALANCES = 439
CHAIN_HASH = r'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
BTC_CHAIN_HASH = CHAIN_HASH
foaf_network = None

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


# TODO: remove when finished, or keep for test cases
def list_funds_mock():
    """"read funds from file"""
    dir_path = os.path.dirname(os.path.realpath(__file__))
    file_name = os.path.join(dir_path, "funds.json")
    with open(file_name, 'r') as funds_file:
        data = funds_file.read()

    return json.loads(data)


# TODO: we need to extend this, if we want to handle multiple channels per peer
def get_channel(channels, peer_id):
    """"searches for ONE channel with the given  peer_id"""
    for ch in channels:
        if ch["peer_id"] == peer_id:
            return ch
    return None


def encode_query_foaf_balances(flow_value, amt_to_rebalance):
    """Encode flow_value and amt_to_rebalance"""
    """
    H ->    type: short
    32s ->  chain_hash: 32byte char
    c ->    flow_value: char
    Q ->    amt_to_rebalance: unsigned long long
    """
    global QUERY_FOAF_BALANCES
    global CHAIN_HASH
    return hexlify(
        struct.pack("!H32scQ", QUERY_FOAF_BALANCES, CHAIN_HASH.encode('ASCII'), flow_value, amt_to_rebalance)).decode(
        'ASCII')


def decode_query_foaf_balances(data):
    """Decode query_foaf_balances. Return type, chain_hash, flow_value and amt_to_rebalance"""
    msg_type, chain_hash, flow, amt = struct.unpack("!H32scQ", unhexlify(data.encode('ASCII')))
    chain_hash = chain_hash.decode('ASCII')
    return msg_type, chain_hash, flow, amt


def get_flow_value(flow):
    if type(flow) is not int:
        return None

    if flow == 1:
        return b'\x01'
    elif flow == 0:
        return b'\x00'
    return None


def get_amount(amt):
    if type(amt) is not int or amt <= 0:
        return None
    return amt


def log_error(msg):
    plugin.log("Error in balancesharing plugin: {msg}".format(msg=msg))


@plugin.method("foafbalance")
def foafbalance(plugin, flow, amount):
    """gets the balance of our friends channels"""
    # Read input data
    flow_value = get_flow_value(flow)
    if flow_value is None:
        log_error("argument 'flow_value' for function 'foafbalance' was not 0 or 1")
        return

    amt_to_rebalance = get_amount(amount)
    if amt_to_rebalance is None:
        log_error("argument 'amt_to_rebalance' for function 'foafbalance' was not valid")
        return

    plugin.log("Input data: {flow_value} and {amt_to_rebalance}".format(
        flow_value=flow_value,
        amt_to_rebalance=amt_to_rebalance
    ))

    data = encode_query_foaf_balances(flow_value, amt_to_rebalance)

    # todo: remove. only for debugging
    msg_type, chain_hash, new_flow_value, new_amt_to_rebalance = decode_query_foaf_balances(data)
    plugin.log(str(data))
    plugin.log("New values: {msg_type} -- {chain_hash} -- {flow_value} -- {amt_to_rebalance}".format(
        msg_type=msg_type,
        chain_hash=chain_hash,
        flow_value=new_flow_value,
        amt_to_rebalance=new_amt_to_rebalance
    ))

    global foaf_network
    foaf_network = nx.DiGraph()

    for peer in plugin.rpc.listpeers()["peers"]:
        # check if peer is the desired state
        if not peer["connected"] or not has_feature(peer["features"]):
            continue
        peer_id = peer["id"]

        res = plugin.rpc.dev_sendcustommsg(peer_id, data)
        plugin.log("RPC response" + str(res))

    nid = plugin.rpc.getinfo()["id"]
    reply = {"id": nid, "change": nid}
    return reply


def get_message_type(message):
    """takes the 4 hex digits of a string and returns them as an integer
    if they are a well known message type"""
    assert len(message) > 4
    message_type = message[:4]
    return struct.unpack(">H", unhexlify(message_type.encode('ASCII')))[0]


def get_message_payload(message):
    assert len(message) > 4
    return message[4:]


def helper_compute_node_parameters(channels):
    """
    computes the total funds (\tau) and the total capacity of a node (\kappa)
    channels: is a list of local channels. Entries are formatted as in `listunfunds` API call
    returns total capacity (\kappa) and total funds (\tau) of the node as integers in satoshis.
    """
    kappa = sum(x["channel_total_sat"] for x in channels)
    tau = sum(x["channel_sat"] for x in channels)
    return kappa, tau


def helper_compute_channel_balance_coefficients(channels):
    # assign zetas to channels:
    for c in channels:
        c["zeta"] = float(c["channel_sat"]) / c["channel_total_sat"]
    return channels


def handle_query_foaf_balances(flow_value, amt_to_rebalance, plugin):
    if flow_value == b'\x00':
        plugin.log("compute channels on which I want {} satoshis incoming while rebalancing".format(
            amt_to_rebalance))
    elif flow_value == b'\x01':
        plugin.log("compute channels on which I want to forward {} satoshis  while rebalancing".format(
            amt_to_rebalance))

    _, channels = get_funds(plugin)

    kappa, tau = helper_compute_node_parameters(channels)
    nu = float(tau) / kappa
    channels = helper_compute_channel_balance_coefficients(channels)

    result = []
    for channel in channels:
        reserve = int(int(channel["channel_total_sat"]) * 0.01) + 1
        if flow_value == 1:
            if channel["zeta"] > nu:
                if int(channel["channel_sat"]) > amt_to_rebalance + reserve:
                    result.append(channel["short_channel_id"])
        elif flow_value == 0:
            if channel["zeta"] < nu:
                if int(channel["channel_total_sat"]) - int(channel["channel_sat"]) > amt_to_rebalance + reserve:
                    result.append(channel["short_channel_id"])
    plugin.log("{} of {} channels are good for rebalancing {} satoshis they are: {}".format(
        len(result), len(channels), amt_to_rebalance, ", ".join(result)))
    return result


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
    global BTC_CHAIN_HASH
    plugin.log("Got a custom message {msg} from peer {peer_id}".format(
        msg=message,
        peer_id=peer_id
    ))
    # message has to be at least 6 bytes. 4 bytes prefix and 2 bytes for the type
    assert len(message) > 12
    # remove prefix:
    message = message[8:]
    message_type = get_message_type(message)
    # message_payload = get_message_payload(message)

    # query_foaf_balances message has type 437 which is 01b5 in hex
    if message_type == QUERY_FOAF_BALANCES:
        plugin.log("received query_foaf_balances message")
        _, chain_hash, flow, amt = decode_query_foaf_balances(message)

        if chain_hash == BTC_CHAIN_HASH:
            result = handle_query_foaf_balances(flow, amt, plugin)
            send_reply_foaf_balances(peer_id, result, plugin)
        else:
            plugin.log("not handling non bitcoin chains for now")

    elif message_type == REPLY_FOAF_BALANCES:
        plugin.log("received a reply_foaf_balances message")

    plugin.log(message)
    plugin.log(str(type(message)))
    return {'result': 'continue'}


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("Plugin balancesharing.py initialized")


plugin.run()
