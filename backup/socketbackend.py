from collections import namedtuple
import json
import logging
import socket
import re
import struct
import time
from typing import Tuple, Iterator
from urllib.parse import urlparse, parse_qs

from backend import Backend, Change
from protocol import (
    PacketType,
    PKT_CHANGE_TYPES,
    change_from_packet,
    packet_from_change,
    send_packet,
    recv_packet,
)

# Total number of reconnection tries
RECONNECT_TRIES = 5

# Delay in seconds between reconnections (initial)
RECONNECT_DELAY = 5

# Scale delay factor after each failure
RECONNECT_DELAY_BACKOFF = 1.5

HostPortInfo = namedtuple("HostPortInfo", ["host", "port", "addrtype"])
SocketURLInfo = namedtuple("SocketURLInfo", ["target", "proxytype", "proxytarget"])

# Network address type.


class AddrType:
    IPv4 = 0
    IPv6 = 1
    NAME = 2


# Proxy type. Only SOCKS5 supported at the moment as this is sufficient for Tor.


class ProxyType:
    DIRECT = 0
    SOCKS5 = 1


def parse_host_port(path: str) -> HostPortInfo:
    """Parse a host:port pair."""
    if path.startswith("["):  # bracketed IPv6 address
        eidx = path.find("]")
        if eidx == -1:
            raise ValueError("Unterminated bracketed host address.")
        host = path[1:eidx]
        addrtype = AddrType.IPv6
        eidx += 1
        if eidx >= len(path) or path[eidx] != ":":
            raise ValueError("Port number missing.")
        eidx += 1
    else:
        eidx = path.find(":")
        if eidx == -1:
            raise ValueError("Port number missing.")
        host = path[0:eidx]
        if re.match(r"\d+\.\d+\.\d+\.\d+$", host):  # matches IPv4 address format
            addrtype = AddrType.IPv4
        else:
            addrtype = AddrType.NAME
        eidx += 1

    try:
        port = int(path[eidx:])
    except ValueError:
        raise ValueError("Invalid port number")

    return HostPortInfo(host=host, port=port, addrtype=addrtype)


def parse_socket_url(destination: str) -> SocketURLInfo:
    """Parse a socket: URL to extract the information contained in it."""
    url = urlparse(destination)
    if url.scheme != "socket":
        raise ValueError("Scheme for socket backend must be socket:...")

    target = parse_host_port(url.path)

    proxytype = ProxyType.DIRECT
    proxytarget = None
    # parse query parameters
    # reject unknown parameters (currently all of them)
    qs = parse_qs(url.query)
    for key, values in qs.items():
        if key == "proxy":  # proxy=socks5:127.0.0.1:9050
            if len(values) != 1:
                raise ValueError("Proxy can only have one value")

            (ptype, ptarget) = values[0].split(":", 1)
            if ptype != "socks5":
                raise ValueError("Unknown proxy type " + ptype)

            proxytype = ProxyType.SOCKS5
            proxytarget = parse_host_port(ptarget)
        else:
            raise ValueError("Unknown query string parameter " + key)

    return SocketURLInfo(target=target, proxytype=proxytype, proxytarget=proxytarget)


class SocketBackend(Backend):
    def __init__(self, destination: str, create: bool):
        self.version = None
        self.prev_version = None
        self.destination = destination
        self.url = parse_socket_url(destination)
        self.connect()

    def connect(self):
        if self.url.proxytype == ProxyType.DIRECT:
            if self.url.target.addrtype == AddrType.IPv6:
                self.sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            else:  # TODO NAME is assumed to be IPv4 for now
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            assert self.url.proxytype == ProxyType.SOCKS5
            import socks

            self.sock = socks.socksocket()
            self.sock.set_proxy(
                socks.SOCKS5, self.url.proxytarget.host, self.url.proxytarget.port
            )

        logging.info(
            "Connecting to {}:{} (addrtype {}, proxytype {}, proxytarget {})...".format(
                self.url.target.host,
                self.url.target.port,
                self.url.target.addrtype,
                self.url.proxytype,
                self.url.proxytarget,
            )
        )
        self.sock.connect((self.url.target.host, self.url.target.port))
        logging.info("Connected to {}".format(self.destination))

    def _send_packet(self, typ: int, payload: bytes) -> None:
        send_packet(self.sock, typ, payload)

    def _recv_packet(self) -> Tuple[int, bytes]:
        return recv_packet(self.sock)

    def initialize(self) -> bool:
        """
        Initialize socket backend by request current metadata from server.
        """
        logging.info("Initializing backend")
        self._request_metadata()
        logging.info(
            "Initialized SocketBackend: protocol={}, version={}, prev_version={}, version_count={}".format(
                self.protocol, self.version, self.prev_version, self.version_count
            )
        )
        return True

    def _request_metadata(self) -> None:
        self._send_packet(PacketType.REQ_METADATA, b"")
        (typ, payload) = self._recv_packet()
        assert typ == PacketType.METADATA
        self.protocol, self.version, self.prev_version, self.version_count = (
            struct.unpack("!IIIQ", payload)
        )

    def add_change(self, entry: Change) -> bool:
        typ, payload = packet_from_change(entry)

        base_version = self.version
        retry = 0
        retry_delay = RECONNECT_DELAY
        need_connect = False
        while True:  # Retry loop
            try:
                if need_connect:
                    self.connect()
                    # Request metadata, to know where we stand
                    self._request_metadata()
                    if self.version == entry.version:
                        # If the current version at the server side matches the version of the
                        # entry, the packet was succesfully sent and processed and the error
                        # happened afterward. Nothing left to do.
                        return True
                    elif base_version == self.version:
                        # The other acceptable option is that the current version still matches
                        # that on the server side. Then we retry.
                        pass
                    else:
                        raise Exception(
                            "Unexpected backup version {} after reconnect".format(
                                self.version
                            )
                        )

                self._send_packet(typ, payload)
                # Wait for change to be acknowledged before continuing.
                (typ, _) = self._recv_packet()
                assert typ == PacketType.ACK
            except (BrokenPipeError, OSError):
                pass
            else:
                break

            if retry == RECONNECT_TRIES:
                logging.error(
                    "Connection was lost while sending change (giving up after {} retries)".format(
                        retry
                    )
                )
                raise IOError("Connection was lost while sending change")

            retry += 1
            logging.warning(
                "Connection was lost while sending change (retry {} of {}, will try again after {} seconds)".format(
                    retry, RECONNECT_TRIES, retry_delay
                )
            )
            time.sleep(retry_delay)
            retry_delay *= RECONNECT_DELAY_BACKOFF
            need_connect = True

        self.prev_version = self.version
        self.version = entry.version
        return True

    def rewind(self) -> bool:
        """Rewind to previous version."""
        version = struct.pack("!I", self.prev_version)
        self._send_packet(PacketType.REWIND, version)
        # Wait for change to be acknowledged before continuing.
        (typ, _) = self._recv_packet()
        assert typ == PacketType.ACK
        return True

    def stream_changes(self) -> Iterator[Change]:
        self._send_packet(PacketType.RESTORE, b"")
        version = -1
        while True:
            (typ, payload) = self._recv_packet()
            if typ in PKT_CHANGE_TYPES:
                change = change_from_packet(typ, payload)
                version = change.version
                yield change
            elif typ == PacketType.DONE:
                break
            else:
                raise ValueError("Unknown entry type {}".format(typ))

        if version != self.version:
            raise ValueError(
                "Versions do not match up: restored version {}, backend version {}".format(
                    version, self.version
                )
            )
        assert version == self.version

    def compact(self):
        self._send_packet(PacketType.COMPACT, b"")
        (typ, payload) = self._recv_packet()
        assert typ == PacketType.COMPACT_RES
        return json.loads(payload.decode())
