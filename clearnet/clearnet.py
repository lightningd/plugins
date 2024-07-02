#!/usr/bin/env python3
import socket
from contextlib import closing

from pyln.client import Plugin, RpcError

plugin = Plugin()


def get_address_type(addrstr: str):
    """I know this can be more sophisticated, but works"""
    if ".onion:" in addrstr:
        return "tor"
    if addrstr[0].isdigit():
        return "ipv4"
    if addrstr.startswith("["):
        return "ipv6"
    return "dns"


# taken from:
# https://stackoverflow.com/questions/19196105/how-to-check-if-a-network-port-is-open
def check_socket(host: str, port: int, timeout: float = None):
    """Checks if a socket can be opened to a host"""
    if host.count(".") == 3:
        proto = socket.AF_INET
    if host.count(":") > 1:
        proto = socket.AF_INET6
    with closing(socket.socket(proto, socket.SOCK_STREAM)) as sock:
        if timeout is not None:
            sock.settimeout(timeout)  # seconds (float)
        if sock.connect_ex((host, port)) == 0:
            return True
        else:
            return False


def clearnet_pid(peer: dict, messages: list):
    peer_id = peer["id"]
    if not peer["connected"]:
        messages += [f"Peer is not conencted: {peer_id}"]
        return False
    if get_address_type(peer["netaddr"][0]) != "tor":
        messages += [f"Already connected via clearnet: {peer_id}"]
        return True

    # lets check what gossip knows about this peer
    nodes = plugin.rpc.listnodes(peer_id)["nodes"]
    if len(nodes) == 0:
        messages += [f"Error: No gossip for: {peer_id}"]
        return
    addrs = [a for a in nodes[0]["addresses"] if not a["type"].startswith("tor")]
    if len(addrs) == 0:
        messages += [f"Error: No clearnet addresses known for: {peer_id}"]
        return

    # now check addrs for open ports
    for addr in addrs:
        if addr["type"] == "dns":
            messages += [f"TODO: DNS lookups for: {addr['address']}"]
            continue
        if check_socket(addr["address"], addr["port"], 2.0):
            # disconnect
            result = plugin.rpc.disconnect(peer_id, True)
            if len(result) != 0:
                messages += [f"Error: Can't disconnect: {peer_id} {result}"]
                continue

            # try clearnet connection
            try:
                result = plugin.rpc.connect(peer_id, addr["address"], addr["port"])
                newtype = result["address"]["type"]
                if not newtype.startswith("tor"):
                    messages += [
                        f"Established clearnet connection for: {peer_id} with {newtype}"
                    ]
                    return True
            except RpcError:  # we got an connection error, try reconnect
                messages += [
                    f"Error: Connection failed for: {peer_id} with {addr['type']}"
                ]
                try:
                    result = plugin.rpc.connect(peer_id)  # without address
                    newtype = result["address"]["type"]
                    if not newtype.startswith("tor"):
                        messages += [
                            f"Established clearnet connection for: {peer_id} with {newtype}"
                        ]
                        return True
                except RpcError:  # we got a reconnection error
                    messages += [f"Error: Reconnection failed for: {peer_id}"]
                    continue
                messages += [f"Reconnected: {peer_id} with {newtype}"]
                continue
    return False


@plugin.method("clearnet")
def clearnet(plugin: Plugin, peer_id: str = None):
    """Enforce a clearnet connection on all peers or a given `peer_id`."""
    if peer_id is None:
        peers = plugin.rpc.listpeers(peer_id)["peers"]
    else:
        if not isinstance(peer_id, str) or len(peer_id) != 66:
            return f"Error: Invalid peer_id: {peer_id}"
        peers = plugin.rpc.listpeers(peer_id)["peers"]
        if len(peers) == 0:
            return f"Error: peer not found: {peer_id}"

    messages = []
    for peer in peers:
        clearnet_pid(peer, messages)
    return messages


@plugin.init()
def init(options: dict, configuration: dict, plugin: Plugin, **kwargs):
    plugin.log("clearnet enforcer plugin initialized")


plugin.run()
