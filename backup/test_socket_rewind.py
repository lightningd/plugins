"""Remote backup rewind must reset the retry baseline.

These are synthetic transport journeys; full lightningd/backup-cli integration
is covered separately.
"""
import struct

import pytest

import socketbackend
from backend import Change
from protocol import PacketType


@pytest.mark.parametrize("accepted_before_disconnect", [False, True])
def test_rewind_replacement_reconnect(monkeypatch, accepted_before_disconnect):
    # A backup was one uncommitted write ahead when lightningd restarted.
    remote = {"version": 11, "prev": 10, "last_change": None}
    backend = object.__new__(socketbackend.SocketBackend)
    backend.version = 11
    backend.prev_version = 10
    backend.version_count = 11
    replies = []
    connections = []

    def send(typ, payload):
        if typ == PacketType.REWIND:
            (target,) = struct.unpack("!I", payload)
            assert target == remote["prev"]
            remote["version"] = target
            remote["prev"] = 0
            replies.append((PacketType.ACK, struct.pack("!I", target)))
        elif typ == PacketType.REQ_METADATA:
            replies.append(
                (
                    PacketType.METADATA,
                    struct.pack("!IIIQ", 1, remote["version"], remote["prev"], 11),
                )
            )
        elif typ == PacketType.CHANGE:
            (target,) = struct.unpack("!I", payload[:4])
            if remote["last_change"] is None:
                remote["last_change"] = "interrupted"
                if accepted_before_disconnect:
                    remote["prev"] = remote["version"]
                    remote["version"] = target
                replies.append(BrokenPipeError("lost reply or request"))
            else:
                assert remote["version"] == target - 1
                remote["prev"] = remote["version"]
                remote["version"] = target
                replies.append((PacketType.ACK, struct.pack("!I", target)))
        else:
            raise AssertionError("Unexpected packet type {}".format(typ))

    def receive():
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(backend, "_send_packet", send)
    monkeypatch.setattr(backend, "_recv_packet", receive)
    monkeypatch.setattr(backend, "connect", lambda: connections.append(True))
    monkeypatch.setattr(socketbackend.time, "sleep", lambda _: None)

    assert backend.rewind()
    assert (backend.version, backend.prev_version) == (10, 0)
    assert backend.add_change(Change(11, None, ["SELECT 1"]))
    assert (backend.version, backend.prev_version) == (11, 10)
    assert (remote["version"], remote["prev"]) == (11, 10)
    assert connections == [True]


def test_rewind_rejects_mismatched_server_ack(monkeypatch):
    backend = object.__new__(socketbackend.SocketBackend)
    backend.version = 11
    backend.prev_version = 10
    monkeypatch.setattr(backend, "_send_packet", lambda typ, payload: None)
    monkeypatch.setattr(
        backend,
        "_recv_packet",
        lambda: (PacketType.ACK, struct.pack("!I", 11)),
    )
    with pytest.raises(ValueError, match="Unexpected backup version"):
        backend.rewind()
    assert (backend.version, backend.prev_version) == (11, 10)
