#!/usr/bin/env python3
from inotify import constants
from inotify.adapters import Inotify
from pyln.client import Plugin
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
                length = length & (~0x80000000) & (~0x40000000)

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

                if length > MAX_MSG_SIZE:
                    logging.warn(
                        f"Unreasonably large message type {typ} at position {self.pos} ({length} bytes), skipping"
                    )
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


class Flusher(Thread):
    def __init__(self, engine):
        Thread.__init__(self)
        self.engine = engine
        self.session_maker = sessionmaker(bind=engine)
        self.session = None

    def run(self):
        logging.info("Starting flusher")
        ft = FileTailer('gossip_store')
        last_flush = time.time()

        self.session = self.session_maker()
        for i, e in enumerate(ft.tail()):
            self.store(e)

            if last_flush < time.time() - 10:
                self.session.commit()
                self.session = self.session_maker()
                last_flush = time.time()

        logging.warn("Filetailer exited...")

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
            logging.warn(f"Exception parsing gossip message: {e}")


@plugin.init()
def init(plugin, configuration, options):
    print(options)
    engine = create_engine(options['historian-dsn'], echo=False)
    Base.metadata.create_all(engine)
    plugin.engine = engine
    Flusher(engine).start()


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
