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
import time
from binascii import hexlify, unhexlify

QUERY_FOAF_BALANCES = 437
REPLY_FOAF_BALANCES = 439
CHAIN_HASH = r'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
BTC_CHAIN_HASH = CHAIN_HASH
# TODO: replace with plugin.rpc.listchannels(short_channel_id)
CHANNEL_INDEX = {}

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


def get_other_node(node_id, short_channel_id):
    channel = CHANNEL_INDEX[short_channel_id]
    if channel == None:
        return None
    if channel["source"] == node_id:
        return channel["destination"]
    if channel["destination"] == node_id:
        return channel["source"]
    return None


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


def pack_channels(channels, plugin):
    # structure: blockheight 4 byte, index 2 byte, output 2 byte
    channels_packed = []
    for ch in channels:
        nums = ch.split('x')
        if len(nums) != 3:
            break
        ch_packed = struct.pack("!LHH", int(nums[0]),
                                int(nums[1]), int(nums[2]))
        channels_packed.append(ch_packed)
        plugin.log("channel: " + ch + " " + str(ch_packed))

    return channels_packed


def unpack_channels(channels, plugin):
    res = []
    for channel in channels:
        byte_channel = struct.pack("!Q", channel)
        vals = struct.unpack("!LHH", byte_channel)
        short_channel_id = "x".join([str(x) for x in vals])
        res.append(short_channel_id)
    plugin.log(" ".join(res))
    return res


def decode_reply_foaf_balances(data, plugin):
    """Decode query_foaf_balances. Return type, chain_hash, flow_value and amt_to_rebalance"""
    # first part is 53 bytes big -> 106 characters
    assert len(data) >= 106

    first_part = data[:106]
    second_part = data[106:]
    plugin.log("Splitting data 1")
    plugin.log(first_part)
    msg_type, chain_hash, flow, timestamp, amt, num_channels\
        = struct.unpack("!H32scQQH", unhexlify(first_part.encode('ASCII')))
    # plugin.log("Msg type: " + str(msg_type))
    plugin.log("Splitting data 2")
    chain_hash = chain_hash.decode('ASCII')
    plugin.log("Splitting data 3")

    unpack_type = '!' + 'Q' * num_channels
    plugin.log(unpack_type)
    plugin.log(str(num_channels))
    plugin.log(str(len(second_part)))
    short_channel_ids = struct.unpack(
        unpack_type, unhexlify(second_part.encode('ASCII')))

    return msg_type, chain_hash, flow, timestamp, amt, short_channel_ids


def encode_reply_foaf_balances(short_channels, flow_value, amt_to_rebalance, plugin):
    """Encode flow_value and amt_to_rebalance"""
    """
    H ->        type: short
    32s ->      chain_hash: 32byte char
    c ->        flow_value: char
    Q ->        timestamp: unsigned long
    Q ->        amt_to_rebalance: unsigned long long
    H ->        number_of_short_channels: unsigned short
    {len*8}s -> short_channel_id
    """
    global REPLY_FOAF_BALANCES
    global CHAIN_HASH

    """
    fund_list = list_funds_mock()
    channels = fund_list["channels"]

    # TODO: remove mock
    mock_short_channels = []
    for ch in channels:
        mock_short_channels.append(ch["short_channel_id"])
    short_channels = mock_short_channels
    """

    # time.time() returns a float with 4 decimal places
    timestamp = int(time.time() * 1000)
    number_of_short_channels = len(short_channels)
    channel_array_sign = str(number_of_short_channels * 8) + 's'
    plugin.log("Channel sign: {channel_array_sign}"
               .format(channel_array_sign=channel_array_sign))

    packed_first_part = struct.pack("!H32scQQH", REPLY_FOAF_BALANCES, CHAIN_HASH.encode('ASCII'),
                                    flow_value, timestamp, amt_to_rebalance, number_of_short_channels)

    packed_second_part = b''
    packed_chs = pack_channels(short_channels, plugin)
    for ch in packed_chs:
        packed_second_part += ch
    tmp = hexlify(packed_first_part + packed_second_part).decode('ASCII')
    plugin.log(tmp)
    return tmp


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
    msg_type, chain_hash, flow, amt = struct.unpack(
        "!H32scQ", unhexlify(data.encode('ASCII')))
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
    if type(amt) is not int or amt == 0:
        return None
    return amt


def log_error(msg, plugin):
    plugin.log("Error in balancesharing plugin: {msg}".format(msg=msg))


@plugin.method("foafbalance")
def foafbalance(plugin, flow=1, amount=50000):
    """gets the balance of our friends channels"""
    plugin.log("Building query_foaf_balances message...")
    # Read input data
    flow_value = get_flow_value(flow)
    if flow_value is None:
        log_error(
            "argument 'flow_value' for function 'foafbalance' was not 0 or 1", plugin)
        return

    amt_to_rebalance = get_amount(amount)
    if amt_to_rebalance is None:
        log_error(
            "argument 'amt_to_rebalance' for function 'foafbalance' was not valid", plugin)
        return

    data = encode_query_foaf_balances(flow_value, amt_to_rebalance)

    # todo: remove. only for debugging
    msg_type, chain_hash, new_flow_value, new_amt_to_rebalance = decode_query_foaf_balances(
        data)
    plugin.log("Test decoding: {msg_type} -- {chain_hash} -- {flow_value} -- {amt_to_rebalance}".format(
        msg_type=msg_type,
        chain_hash=chain_hash,
        flow_value=new_flow_value,
        amt_to_rebalance=new_amt_to_rebalance
    ))

    global foaf_network
    foaf_network = nx.DiGraph()

    counter = 0
    for peer in plugin.rpc.listpeers()["peers"]:
        # check if peer is the desired state
        if not peer["connected"] or not has_feature(peer["features"]):
            continue
        peer_id = peer["id"]
        plugin.log(data)
        res = plugin.rpc.dev_sendcustommsg(peer_id, data)
        plugin.log("Sent query_foaf_balances message to {peer_id}. Response: {res}".format(
            peer_id=peer_id,
            res=res
        ))

        counter = counter + 1

    nid = plugin.rpc.getinfo()["id"]
    reply = {"id": nid, "num_sent_queries": counter}
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
    else:
        return []

    _, channels = get_funds(plugin)

    kappa, tau = helper_compute_node_parameters(channels)
    nu = float(tau) / kappa
    channels = helper_compute_channel_balance_coefficients(channels)

    channel_ids = []
    for channel in channels:
        reserve = int(int(channel["channel_total_sat"]) * 0.01) + 1
        if flow_value == b'\x01':
            if channel["zeta"] > nu:
                if int(channel["channel_sat"]) > amt_to_rebalance + reserve:
                    channel_ids.append(channel["short_channel_id"])
        elif flow_value == b'\x00':
            if channel["zeta"] < nu:
                if int(channel["channel_total_sat"]) - int(channel["channel_sat"]) > amt_to_rebalance + reserve:
                    channel_ids.append(channel["short_channel_id"])
    plugin.log("{} of {} channels are good for rebalancing {} satoshis they are: {}".format(
        len(channel_ids), len(channels), amt_to_rebalance, ", ".join(channel_ids)))
    return channel_ids


def send_reply_foaf_balances(peer, amt, flow, channels, plugin):
    msg = encode_reply_foaf_balances(channels, flow, amt, plugin)
    msg_type, chain_hash, flow, timestamp, amt, short_channel_ids\
        = decode_reply_foaf_balances(msg, plugin)

    for ids in unpack_channels(short_channel_ids, plugin):
        plugin.log(str(ids))

    # TODO: CHECK if 107b is the correct little endian of 439
    res = plugin.rpc.dev_sendcustommsg(peer, "107b123412341234")
    plugin.log("Sent query_foaf_balances message to {peer_id}. Response: {res}".format(
        peer_id=peer,
        res=res
    ))
    reply = {"peer_id": peer, "response": res}
    return reply


def decode_reply_foaf_balances_mock(message):
    """
    * [`chain_hash: chain_hash`]
    * [`byte: flow_value`]
    * [`u64: timestamp`]
    * [`u64: amt_to_rebalance`]
    * [`u16:len`]
    * [`len*u64: short_channel_id`]
    """
    chain_hash = CHAIN_HASH
    flow_value = 1
    ts = int(time.time() * 1000)
    amt_to_rebalance = 50000
    short_channel_ids = list(CHANNEL_INDEX.keys())
    return chain_hash, flow_value, ts, amt_to_rebalance, short_channel_ids


@plugin.hook('peer_connected')
def on_connected(plugin, **kwargs):
    plugin.log("GOT PEER CONNECTION HOOK")
    return {'result': 'continue'}


@plugin.hook('custommsg')
def on_custommsg(peer_id, message, plugin, **kwargs):
    global BTC_CHAIN_HASH
    global foaf_network
    plugin.log("Got a custom message {msg} from peer {peer_id}".format(
        msg=message,
        peer_id=peer_id
    ))
    # TODO: Remove to stop mocking
    mock_peer_id = "03efccf2c383d7bf340da9a3f02e2c23104a0e4fe8ac1a880c8e2dc92fbdacd9df"
    plugin.log("switched peer_id to {} for testing".format(peer_id))
    # message has to be at least 6 bytes. 4 bytes prefix and 2 bytes for the type
    assert len(message) > 12
    # remove prefix:
    message = message[8:]
    message_type = get_message_type(message)
    # message_payload = get_message_payload(message)

    # query_foaf_balances message has type 437 which is 01b5 in hex
    return_value = {}
    if message_type == QUERY_FOAF_BALANCES:
        plugin.log("received query_foaf_balances message")
        _, chain_hash, flow, amt = decode_query_foaf_balances(message)

        if chain_hash == BTC_CHAIN_HASH:
            result = handle_query_foaf_balances(flow, amt, plugin)
            plugin.log("HALLO" + str(result))
            r = send_reply_foaf_balances(peer_id, amt, flow, result, plugin)
            return_value = {"result": r}
        else:
            plugin.log("not handling non bitcoin chains for now")

    elif message_type == REPLY_FOAF_BALANCES:
        _, chain_hash, flow_value, ts, amt_to_rebalance, short_channel_ids = decode_reply_foaf_balances(
            message, plugin)
        # decode_reply_foaf_balances_mock(message)
        plugin.log("received a reply_foaf_balances message")
        for short_channel_id in short_channel_ids:
            # TODO: remove mock
            partner = get_other_node(mock_peer_id, short_channel_id)
            if partner is None:
                continue
            # TODO: shall we include the timestamp the the edges?
            # TODO: an edge MUST only exist in one direction
            if flow_value == 1:
                foaf_network.add_edge(peer_id, partner)
            else:
                foaf_network.add_edge(partner, peer_id)
        # TODO invoke rebalance path finding logic (but with whome? need a peer to which an HTLC is stuck)
        plugin.log("FOAF Graph now has {} channels".format(
            len(foaf_network.edges())))

    return return_value


def reindex_channels(plugin):
    plugin.log("indexing payment channels by short channel id")
    # TODO: REMOVE MOCK
    # channels=plugin.rpc.listchannels()["channels"]
    dir_path = os.path.dirname(os.path.realpath(__file__))
    file_name = os.path.join(dir_path, "channels.json")
    with open(file_name, 'r') as funds_file:
        data = funds_file.read()

    channels = json.loads(data)["channels"]

    for channel in channels:
        short_channel_id = channel["short_channel_id"]
        CHANNEL_INDEX[short_channel_id] = channel


@plugin.init()
def init(options, configuration, plugin):
    plugin.log("Plugin balancesharing.py initialized")
    reindex_channels(plugin)


plugin.run()
