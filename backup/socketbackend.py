import json
import logging, socket, struct
from typing import Tuple, Iterator
from urllib.parse import urlparse

from backend import Backend, Change
from protocol import PacketType, recvall, PKT_CHANGE_TYPES, change_from_packet, packet_from_change, send_packet, recv_packet

class SocketBackend(Backend):
    def __init__(self, destination: str, create: bool):
        self.version = None
        self.prev_version = None
        self.destination = destination
        self.url = urlparse(self.destination)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        (host, port) = self.url.path.split(':')
        logging.info('Initialized socket backend')
        self.sock.connect((host, int(port)))
        logging.info('Connected to {}'.format(destination))

    def _send_packet(self, typ: int, payload: bytes) -> None:
        send_packet(self.sock, typ, payload)

    def _recv_packet(self) -> Tuple[int, bytes]:
        return recv_packet(self.sock)

    def initialize(self) -> bool:
        '''
        Initialize socket backend by request current metadata from server.
        '''
        logging.info('Initializing backend')
        self._send_packet(PacketType.REQ_METADATA, b'')
        (typ, payload) = self._recv_packet()
        assert(typ == PacketType.METADATA)
        self.protocol, self.version, self.prev_version, self.version_count = struct.unpack("!IIIQ", payload)
        logging.info('Initialized SocketBackend: protocol={}, version={}, prev_version={}, version_count={}'.format(
            self.protocol, self.version, self.prev_version, self.version_count
        ))
        return True

    def add_change(self, entry: Change) -> bool:
        typ, payload = packet_from_change(entry)
        self._send_packet(typ, payload)
        # Wait for change to be acknowledged before continuing.
        (typ, _) = self._recv_packet()
        assert(typ == PacketType.ACK)
        return True

    def rewind(self) -> bool:
        '''Rewind to previous version.'''
        version = struct.pack("!I", self.prev_version)
        self._send_packet(PacketType.REWIND, version)
        # Wait for change to be acknowledged before continuing.
        (typ, _) = self._recv_packet()
        assert(typ == PacketType.ACK)
        return True

    def stream_changes(self) -> Iterator[Change]:
        self._send_packet(PacketType.RESTORE, b'')
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
            raise ValueError("Versions do not match up: restored version {}, backend version {}".format(version, self.version))
        assert(version == self.version)

    def compact(self):
        self._send_packet(PacketType.COMPACT, b'')
        (typ, payload) = self._recv_packet()
        assert(typ == PacketType.COMPACT_RES)
        return json.loads(payload.decode())
