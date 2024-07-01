"""
Socket-based remote backup protocol. This is used to create a connection to a backup backend, and send it incremental database updates.
"""

import socket
import struct
from typing import Tuple
import zlib

from backend import Change


class PacketType:
    CHANGE = 0x01
    SNAPSHOT = 0x02
    REWIND = 0x03
    REQ_METADATA = 0x04
    RESTORE = 0x05
    ACK = 0x06
    NACK = 0x07
    METADATA = 0x08
    DONE = 0x09
    COMPACT = 0x0A
    COMPACT_RES = 0x0B


PKT_CHANGE_TYPES = {PacketType.CHANGE, PacketType.SNAPSHOT}


def recvall(sock: socket.socket, n: int) -> bytearray:
    """Receive exactly n bytes from a socket."""
    buf = bytearray(n)
    view = memoryview(buf)
    ptr = 0
    while ptr < n:
        count = sock.recv_into(view[ptr:])
        if count == 0:
            raise IOError("Premature end of stream")
        ptr += count
    return buf


def send_packet(sock: socket.socket, typ: int, payload: bytes) -> None:
    sock.sendall(struct.pack("!BI", typ, len(payload)))
    sock.sendall(payload)


def recv_packet(sock: socket.socket) -> Tuple[int, bytes]:
    (typ, length) = struct.unpack("!BI", recvall(sock, 5))
    payload = recvall(sock, length)
    return (typ, payload)


def change_from_packet(typ, payload):
    """Convert a network packet to a Change object."""
    if typ == PacketType.CHANGE:
        (version,) = struct.unpack("!I", payload[0:4])
        payload = zlib.decompress(payload[4:])
        return Change(
            version=version,
            snapshot=None,
            transaction=[t.decode("UTF-8") for t in payload.split(b"\x00")],
        )
    elif typ == PacketType.SNAPSHOT:
        (version,) = struct.unpack("!I", payload[0:4])
        payload = zlib.decompress(payload[4:])
        return Change(version=version, snapshot=payload, transaction=None)
    raise ValueError("Not a change (typ {})".format(typ))


def packet_from_change(entry):
    """Convert a Change object to a network packet."""
    if entry.snapshot is None:
        typ = PacketType.CHANGE
        payload = b"\x00".join([t.encode("UTF-8") for t in entry.transaction])
    else:
        typ = PacketType.SNAPSHOT
        payload = entry.snapshot

    version = struct.pack("!I", entry.version)
    return typ, version + zlib.compress(payload)
