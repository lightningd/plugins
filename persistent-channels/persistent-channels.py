#!/usr/bin/env python3
from pyln.client import Plugin, RpcError
from threading import Timer
import os
import json
import traceback


plugin = Plugin()


def load_state(path):
    try:
        state = json.loads(open(path, "r").read())
    except Exception:
        print("Could not read state file, creating a new one.")
        return {"channels": {}}
    return state


def save_state(path, state):
    """Atomically save the new state to the state_file."""
    tmppath = path + ".tmp"
    with open(tmppath, "w") as f:
        f.write(json.dumps(state, indent=2))
    os.rename(tmppath, path)


def is_connectable(rpc, node_id):
    nodes = rpc.listnodes(node_id)

    if len(nodes) == 0:
        return False

    print(nodes)


def maybe_open_channel(desired, rpc):
    peers = rpc.listpeers(desired["node_id"])["peers"]

    if "satoshi" in desired:
        desired["amount"] = "{}sat".format(desired["satoshi"])
        del desired["satoshi"]

    if peers == []:
        # Need to connect first, and then open a channel
        # if not is_connectable(rpc, desired['node_id']):
        #     print("No address known for {}, cannot connect.".format(desired['node_id']))

        try:
            rpc.connect(desired["node_id"])
        except RpcError as re:
            print("Could not connect to peer: {}".format(re.error))
            return
        peer = rpc.listpeers(desired["node_id"])["peers"][0]
    else:
        peer = peers[0]

    channel_states = [c["state"] for c in peer["channels"]]

    if peer is None or len(peer["channels"]) == 0:
        # Just open it, we don't have one yet
        # TODO(cdecker) Check balance before actually opening
        rpc.fundchannel(**desired)

    elif "CHANNELD_NORMAL" in channel_states:
        # Already in the desired state, nothing to do.
        return
    elif channel_states == ["ONCHAIND"]:
        # If our only channel is in state ONCHAIND it's probably time
        # to open a new one
        rpc.connect(desired["node_id"])
        rpc.fundchannel(**desired)


def check_channels(plugin):
    """Load actual and desired states, and try to reconcile."""
    state = load_state(plugin.state_file)
    print(state)
    for c in state["channels"].values():
        try:
            maybe_open_channel(c, plugin.rpc)
        except Exception:
            plugin.log(f'Error attempting to open a channel with {c["node_id"]}.')
            traceback.print_exc()
    Timer(30, check_channels, args=[plugin]).start()


@plugin.method("addpersistentchannel")
def add_persistent_channel(node_id, satoshi, plugin, feerate="normal", announce=True):
    """Add a persistent channel to the state map.

    The persistent-channels plugin will ensure that the channel is
    opened as soon as possible and re-opened should it get closed. The
    parameters are identical to `fundchannel`.

    """
    state = load_state(plugin.state_file)
    state["channels"][node_id] = {
        "node_id": node_id,
        "satoshi": satoshi,
        "feerate": feerate,
        "announce": announce,
    }
    save_state(plugin.state_file, state)
    maybe_open_channel(state["channels"][node_id], plugin.rpc)


@plugin.init()
def init(options, configuration, plugin):
    # This is the file in which we'll store all of our state (mostly
    # desired channels for now)
    plugin.state_file = os.path.join(
        configuration["lightning-dir"], "persistent-channels.json"
    )
    check_channels(plugin)


plugin.run()
