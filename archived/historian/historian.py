#!/usr/bin/env python3
from inotify import constants
from inotify.adapters import Inotify
import os
from pyln.client import Plugin
import pika
from sqlalchemy import create_engine
from sqlalchemy import desc
from sqlalchemy.orm import sessionmaker
from threading import Thread
from common import Base, ChannelAnnouncement, ChannelUpdate, NodeAnnouncement
import logging
import gossipd
import struct
import time

# Any message that is larger than this threshold will not be processed
# as it bloats the database.
MAX_MSG_SIZE = 1024

plugin = Plugin()


class FsMonitor(Thread):
    def __init__(self):
        pass

    def run(self):
        watch_mask = constants.IN_ALL_EVENTS

        print("Starting FsMonitor")
        i = Inotify()
        i.add_watch('gossip_store', mask=watch_mask)
        for event in i.event_gen(yield_nones=False):
            (e, type_names, path, filename) = event
            if e.mask & constants.IN_DELETE_SELF:
                i.remove_watch('gossip_store')
                i.add_watch('gossip_store', mask=watch_mask)


class FileTailer():
    def __init__(self, filename):
        self.filename = filename
        self.pos = 1
        self.version = None

    def resume(self):
        ev_count = 0
        with open(self.filename, 'rb') as f:
            self.version, = struct.unpack("!B", f.read(1))
            f.seek(self.pos)
            while True:
                skip = False
                diff = 8
                hdr = f.read(8)
                if len(hdr) < 8:
                    break

                length, crc = struct.unpack("!II", hdr)
                if self.version > 3:
                    f.read(4)  # Throw away the CRC
                    diff += 4

                # deleted = (length & 0x80000000 != 0)
                # important = (length & 0x40000000 != 0)
                # dying = (length & 0x08000000 != 0)
                length = length & (~0x80000000) & (~0x40000000) & (~0x08000000)

                msg = f.read(length)

                # Incomplete write, will try again
                if len(msg) < length:
                    logging.debug(
                        f"Partial read: {len(msg)}<{length}, waiting 1 second"
                    )
                    time.sleep(1)
                    f.seek(self.pos)
                    continue

                diff += length

                # Strip eventual wrappers:
                typ, = struct.unpack("!H", msg[:2])
                if self.version <= 3 and typ in [4096, 4097, 4098]:
                    msg = msg[4:]

                self.pos += diff
                if typ in [4101, 3503]:
                    f.seek(self.pos)
                    continue

                if typ in [4102, 4103, 4104, 4105, 4106]:
                    f.seek(self.pos)
                    continue

                if length > MAX_MSG_SIZE:
                    plugin.log(
                        f"Unreasonably large message type {typ} at position {self.pos} ({length} bytes), skipping",
                        level="warn")
                    continue

                ev_count += 1

                yield msg
        logging.debug(
            f"Reached end of {self.filename} at {self.pos} after {ev_count} "
            "new messages, waiting for new fs event"
        )

    def wait_actionable(self, i):
        for event in i.event_gen(yield_nones=False):
            if event[0].mask & constants.IN_DELETE_SELF:
                return 'swap'
            if event[0].mask & constants.IN_MODIFY:
                return 'append'

    def tail(self):
        watch_mask = (constants.IN_ALL_EVENTS ^ constants.IN_ACCESS ^
                      constants.IN_OPEN ^ constants.IN_CLOSE_NOWRITE)
        i = Inotify()
        i.add_watch(self.filename, mask=watch_mask)
        while True:
            # Consume as much as possible.
            yield from self.resume()

            # Now wait for a change that we can react to
            ev = self.wait_actionable(i)

            if ev == 'append':
                continue

            if ev == 'swap':
                # Need to reach around since file-deletion removes C watches,
                # but not the python one...
                try:
                    i.remove_watch(self.filename)
                except Exception:
                    pass
                i.add_watch(self.filename, mask=watch_mask)
                self.pos = 1
                continue


def encode_varint(value):
    """Encode a varint value"""
    result = bytearray()
    while value >= 128:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def field_prefix(index: int, wire_type: int) -> bytes:
    """The T part of the TLV for protobuf encoded fields.
    Bits 0-2 are the type, while greater bits are the varint encoded field index.
    0	VARINT	int32, int64, uint32, uint64, sint32, sint64, bool, enum
    1	I64	fixed64, sfixed64, double
    2	LEN	string, bytes, embedded messages, packed repeated fields
    3	SGROUP	group start (deprecated)
    4	EGROUP	group end (deprecated)
    5	I32	fixed32, sfixed32, float"""
    return encode_varint(index << 3 | wire_type)


def length_delimited(data: bytes) -> bytes:
    """The LV part of the TLV for protobuf encoded fields."""
    if not data:
        return b'\x00'
    return encode_varint(len(data)) + data


def serialize(msg: bytes, node_id: str, network: str) -> bytes:
    # from GL proto/internal.proto:
    # message GossipMessage {
    #   // The raw message as seen on the wire.
    #   bytes raw = 1;
    #
    #   // For private messages such as local addition of a channel we
    #   // want to restrict to the node that originated the message.
    #   bytes node_id = 2;
    #
    #   // Which network was the client configured to follow?
    #   Network network = 3;
    #
    #   // Which peer of the node sent this message?
    #   bytes peer_id = 4;
    # }
    network_encoding = {"bitcoin": 0, "testnet": 1, "regtest": 2, "signet": 3}
    if network in network_encoding:
        active_network = network_encoding[network]
    else:
        active_network = 2
    output = bytearray()
    output.extend(field_prefix(1, 2))         # raw message tag
    output.extend(length_delimited(msg))      # raw msg field
    output.extend(field_prefix(2, 2))         # node_id tag
    output.extend(length_delimited(None))     # leave this empty - all public.
    output.extend(field_prefix(3, 0))         # network in an enum
    output.extend(length_delimited(active_network.to_bytes()))  # network field
    output.extend(field_prefix(4, 2))         # peer_id tag
    if node_id:
        # Add our node_id if we have it (so we know who to blame.)
        output.extend(length_delimited(node_id.encode("utf-8")))
    else:
        output.extend(length_delimited(None))  # our node id not available

    return output


class Flusher(Thread):
    def __init__(self, engine):
        Thread.__init__(self)
        self.engine = engine
        self.session_maker = sessionmaker(bind=engine)
        self.session = None
        self.RABBITMQ_URL = os.environ.get("RABBITMQ_URL")
        self.connection = None
        my_info = plugin.rpc.getinfo()
        if "id" in my_info:
            self.node_id = my_info["id"]
        else:
            self.node_id = None
        if "network" in my_info:
            self.network = my_info["network"]
        else:
            self.network = None

    def rabbitmq_connect(self):
        params = pika.URLParameters(self.RABBITMQ_URL)
        self.connection = pika.BlockingConnection(params)  # default, localhost
        self.channel = self.connection.channel()
        plugin.log(f"message queue connected to {params.host}:{params.port}")

    def run(self):
        logging.info("Starting flusher")
        ft = FileTailer('gossip_store')
        last_flush = time.time()
        total = 0

        self.session = self.session_maker()
        for i, e in enumerate(ft.tail()):
            self.store(e)
            self.publish(e)

            if last_flush < time.time() - 10:
                self.session.commit()
                self.session = self.session_maker()
                last_flush = time.time()

        plugin.log("Filetailer exited...", level="warn")
        if self.connection:
            self.connection.close()
            plugin.log("Rabbitmq connection closed.", level="warn")

    def store(self, raw: bytes) -> None:
        try:
            msg = gossipd.parse(raw)
            cls = None
            if isinstance(msg, gossipd.ChannelUpdate):
                cls = ChannelUpdate

            elif isinstance(msg, gossipd.ChannelAnnouncement):
                cls = ChannelAnnouncement

            elif isinstance(msg, gossipd.NodeAnnouncement):
                cls = NodeAnnouncement
                
            else:
                return;

            self.session.merge(cls.from_gossip(msg, raw))
        except Exception as e:
            logging.warning(f"Exception parsing gossip message: {e}")

    def publish(self, raw: bytes) -> None:
        """Serialize and publish a gossip message to a rabbitmq exchange."""
        if not self.RABBITMQ_URL:
            return

        try:
            msg = gossipd.parse(raw)
            if msg is None:
                return
        except Exception as e:
            logging.warning(f"Could not parse gossip message: {e}")
            return

        if not self.connection or not self.connection.is_open:
            try:
                plugin.log(f"connecting to message queue")
                self.rabbitmq_connect()
            except:
                raise Exception("rabbitmq connection closed")

        for msg_type in [gossipd.ChannelUpdate,
                         gossipd.ChannelAnnouncement,
                         gossipd.NodeAnnouncement]:
            if isinstance(msg, msg_type):
                self.channel.basic_publish(exchange='router.gossip',
                                           # unused by fanout exchange
                                           routing_key='',
                                           body=serialize(raw, self.node_id,
                                                          self.network))
                return



@plugin.init()
def init(plugin, configuration, options):
    print(options)
    try:
        engine = create_engine(options['historian-dsn'], echo=False)
        Base.metadata.create_all(engine)
        plugin.engine = engine
        Flusher(engine).start()
    finally:
        engine.dispose()


@plugin.method('historian-stats')
def stats(plugin):
    engine = plugin.engine
    session_maker = sessionmaker(bind=engine)
    session = session_maker()

    return {
        'channel_announcements': session.query(ChannelAnnouncement).count(),
        'channel_updates': session.query(ChannelUpdate).count(),
        'node_announcements': session.query(NodeAnnouncement).count(),
        'latest_node_announcement': session.query(NodeAnnouncement).order_by(desc(NodeAnnouncement.timestamp)).limit(1).first(),
        'latest_channel_update': session.query(ChannelUpdate).order_by(desc(ChannelUpdate.timestamp)).limit(1).first(),
    }


plugin.add_option(
    'historian-dsn',
    'sqlite:///historian.sqlite3',
    "SQL DSN defining where the gossip data should be stored."
)

if __name__ == "__main__":
    plugin.run()
