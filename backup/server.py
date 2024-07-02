import logging
import socket
import struct
import json
import sys
from typing import Tuple

from backend import Backend
from protocol import (
    PacketType,
    PKT_CHANGE_TYPES,
    change_from_packet,
    packet_from_change,
    send_packet,
    recv_packet,
)


class SystemdHandler(logging.Handler):
    PREFIX = {
        # EMERG <0>
        # ALERT <1>
        logging.CRITICAL: "<2>",
        logging.ERROR: "<3>",
        logging.WARNING: "<4>",
        # NOTICE <5>
        logging.INFO: "<6>",
        logging.DEBUG: "<7>",
        logging.NOTSET: "<7>",
    }

    def __init__(self, stream=sys.stdout):
        self.stream = stream
        logging.Handler.__init__(self)

    def emit(self, record):
        try:
            msg = self.PREFIX[record.levelno] + self.format(record) + "\n"
            self.stream.write(msg)
            self.stream.flush()
        except Exception:
            self.handleError(record)


def setup_server_logging(mode, level):
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())
    mode = mode.lower()
    if mode == "systemd":
        # replace handler with systemd one
        root_logger.handlers = []
        root_logger.addHandler(SystemdHandler())
    else:
        assert mode == "plain"


class SocketServer:
    def __init__(self, addr: Tuple[str, int], backend: Backend) -> None:
        self.backend = backend
        self.addr = addr
        self.bind = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.bind.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.bind.bind(addr)

    def _send_packet(self, typ: int, payload: bytes) -> None:
        send_packet(self.sock, typ, payload)

    def _recv_packet(self) -> Tuple[int, bytes]:
        return recv_packet(self.sock)

    def _handle_conn(self, conn) -> None:
        # Can only handle one connection at a time
        logging.info("Servicing incoming connection")
        self.sock = conn
        while True:
            try:
                (typ, payload) = self._recv_packet()
            except IOError:
                logging.info("Connection closed")
                break
            if typ in PKT_CHANGE_TYPES:
                change = change_from_packet(typ, payload)
                if typ == PacketType.CHANGE:
                    logging.debug("Received CHANGE {}".format(change.version))
                else:
                    logging.info("Received SNAPSHOT {}".format(change.version))
                self.backend.add_change(change)
                self._send_packet(
                    PacketType.ACK, struct.pack("!I", self.backend.version)
                )
            elif typ == PacketType.REWIND:
                logging.info("Received REWIND")
                (to_version,) = struct.unpack("!I", payload)
                if to_version != self.backend.prev_version:
                    logging.info("Cannot rewind to version {}".format(to_version))
                    self._send_packet(
                        PacketType.NACK, struct.pack("!I", self.backend.version)
                    )
                else:
                    self.backend.rewind()
                    self._send_packet(
                        PacketType.ACK, struct.pack("!I", self.backend.version)
                    )
            elif typ == PacketType.REQ_METADATA:
                logging.debug("Received REQ_METADATA")
                blob = struct.pack(
                    "!IIIQ",
                    0x01,
                    self.backend.version,
                    self.backend.prev_version,
                    self.backend.version_count,
                )
                self._send_packet(PacketType.METADATA, blob)
            elif typ == PacketType.RESTORE:
                logging.info("Received RESTORE")
                for change in self.backend.stream_changes():
                    (typ, payload) = packet_from_change(change)
                    self._send_packet(typ, payload)
                self._send_packet(PacketType.DONE, b"")
            elif typ == PacketType.COMPACT:
                logging.info("Received COMPACT")
                stats = self.backend.compact()
                self._send_packet(PacketType.COMPACT_RES, json.dumps(stats).encode())
            elif typ == PacketType.ACK:
                logging.debug("Received ACK")
            elif typ == PacketType.NACK:
                logging.debug("Received NACK")
            elif typ == PacketType.METADATA:
                logging.debug("Received METADATA")
            elif typ == PacketType.COMPACT_RES:
                logging.debug("Received COMPACT_RES")
            else:
                raise Exception("Unknown or unexpected packet type {}".format(typ))
        self.conn = None

    def run(self) -> None:
        self.bind.listen(1)
        logging.info("Waiting for connection on {}".format(self.addr))
        while True:
            conn, _ = self.bind.accept()
            try:
                self._handle_conn(conn)
            except Exception:
                logging.exception("Got exception")
            finally:
                conn.close()
