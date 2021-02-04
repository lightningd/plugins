from collections import namedtuple
import json, logging, socket, re, struct
from typing import Tuple, Iterator
from urllib.parse import urlparse, parse_qs

from backend import Backend, Change
from protocol import PacketType, recvall, PKT_CHANGE_TYPES, change_from_packet, packet_from_change, send_packet, recv_packet

SocketURLInfo = namedtuple('SocketURLInfo', ['host', 'port', 'addrtype'])

class AddrType:
    IPv4 = 0
    IPv6 = 1
    NAME = 2

def parse_socket_url(destination: str) -> SocketURLInfo:
    '''Parse a socket: URL to extract the information contained in it.'''
    url = urlparse(destination)
    if url.scheme != 'socket':
        raise ValueError('Scheme for socket backend must be socket:...')

    if url.path.startswith('['): # bracketed IPv6 address
        eidx = url.path.find(']')
        if eidx == -1:
            raise ValueError('Unterminated bracketed host address.')
        host = url.path[1:eidx]
        addrtype = AddrType.IPv6
        eidx += 1
        if eidx >= len(url.path) or url.path[eidx] != ':':
            raise ValueError('Port number missing.')
        eidx += 1
    else:
        eidx = url.path.find(':')
        if eidx == -1:
            raise ValueError('Port number missing.')
        host = url.path[0:eidx]
        if re.match('\d+\.\d+\.\d+\.\d+$', host): # matches IPv4 address format
            addrtype = AddrType.IPv4
        else:
            addrtype = AddrType.NAME
        eidx += 1

    try:
        port = int(url.path[eidx:])
    except ValueError:
        raise ValueError('Invalid port number')

    # parse query parameters
    # reject unknown parameters (currently all of them)
    qs = parse_qs(url.query)
    if len(qs):
        raise ValueError('Invalid query string')

    return SocketURLInfo(host=host, port=port, addrtype=addrtype)

class SocketBackend(Backend):
    def __init__(self, destination: str, create: bool):
        self.version = None
        self.prev_version = None
        self.destination = destination
        self.url = parse_socket_url(destination)
        if self.url.addrtype == AddrType.IPv6:
            self.sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        else: # TODO NAME is assumed to be IPv4 for now
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        logging.info('Initialized socket backend, connecting to {}:{} (addrtype {})...'.format(
                self.url.host, self.url.port, self.url.addrtype))
        self.sock.connect((self.url.host, self.url.port))
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
