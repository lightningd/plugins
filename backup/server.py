import logging, socket, struct
import json
from typing import Tuple

from backend import Backend
from protocol import PacketType, recvall, PKT_CHANGE_TYPES, change_from_packet, packet_from_change, send_packet, recv_packet

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
        logging.info('Servicing incoming connection')
        self.sock = conn
        while True:
            try:
                (typ, payload) = self._recv_packet()
            except IOError as e:
                logging.info('Connection closed')
                break
            if typ in PKT_CHANGE_TYPES:
                change = change_from_packet(typ, payload)
                if typ == PacketType.CHANGE:
                    logging.info('Received CHANGE {}'.format(change.version))
                else:
                    logging.info('Received SNAPSHOT {}'.format(change.version))
                self.backend.add_change(change)
                self._send_packet(PacketType.ACK, struct.pack("!I", self.backend.version))
            elif typ == PacketType.REWIND:
                logging.info('Received REWIND')
                to_version, = struct.unpack('!I', payload)
                if to_version != self.backend.prev_version:
                    logging.info('Cannot rewind to version {}'.format(to_version))
                    self._send_packet(PacketType.NACK, struct.pack("!I", self.backend.version))
                else:
                    self.backend.rewind()
                    self._send_packet(PacketType.ACK, struct.pack("!I", self.backend.version))
            elif typ == PacketType.REQ_METADATA:
                logging.info('Received REQ_METADATA')
                blob = struct.pack("!IIIQ", 0x01, self.backend.version,
                           self.backend.prev_version,
                           self.backend.version_count)
                self._send_packet(PacketType.METADATA, blob)
            elif typ == PacketType.RESTORE:
                logging.info('Received RESTORE')
                for change in self.backend.stream_changes():
                    (typ, payload) = packet_from_change(change)
                    self._send_packet(typ, payload)
                self._send_packet(PacketType.DONE, b'')
            elif typ == PacketType.COMPACT:
                logging.info('Received COMPACT')
                stats = self.backend.compact()
                self._send_packet(PacketType.COMPACT_RES, json.dumps(stats).encode())
            elif typ == PacketType.ACK:
                logging.info('Received ACK')
            elif typ == PacketType.NACK:
                logging.info('Received NACK')
            elif typ == PacketType.METADATA:
                logging.info('Received METADATA')
            elif typ == PacketType.COMPACT_RES:
                logging.info('Received COMPACT_RES')
            else:
                raise Exception('Unknown or unexpected packet type {}'.format(typ))
        self.conn = None

    def run(self) -> None:
        self.bind.listen(1)
        logging.info('Waiting for connection on {}'.format(self.addr))
        while True:
            conn, _ = self.bind.accept()
            try:
                self._handle_conn(conn)
            except Exception as e:
                logging.exception('Got exception')
            finally:
                conn.close()
