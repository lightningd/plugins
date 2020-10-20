from binascii import hexlify
from datetime import datetime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, BigInteger, SmallInteger, DateTime, BLOB
import parser

Base = declarative_base()


class ChannelUpdate(Base):
    __tablename__ = 'channel_updates'
    scid = Column(BigInteger, primary_key=True)
    direction = Column(SmallInteger, primary_key=True)
    timestamp = Column(DateTime, primary_key=True)
    raw = Column(BLOB)

    @classmethod
    def from_gossip(cls, gcu: parser.ChannelUpdate,
                    raw: bytes) -> 'ChannelUpdate':
        assert(raw[:2] == b'\x01\x02')
        self = ChannelUpdate()
        self.scid = gcu.num_short_channel_id
        self.timestamp = datetime.fromtimestamp(gcu.timestamp)
        self.direction = gcu.direction
        self.raw = raw
        return self

    def to_json(self):
        return {
            'scid': "{}x{}x{}".format(self.scid >> 40, self.scid >> 16 & 0xFFFFFF, self.scid & 0xFFFF),
            'nscid': self.scid,
            'direction': self.direction,
            'timestamp':  self.timestamp.strftime("%Y/%m/%d, %H:%M:%S"),
            'raw': hexlify(self.raw).decode('ASCII'),
        }


class ChannelAnnouncement(Base):
    __tablename__ = "channel_announcements"
    scid = Column(BigInteger, primary_key=True)
    raw = Column(BLOB)

    @classmethod
    def from_gossip(cls, gca: parser.ChannelAnnouncement,
                    raw: bytes) -> 'ChannelAnnouncement':
        assert(raw[:2] == b'\x01\x00')
        self = ChannelAnnouncement()
        self.scid = gca.num_short_channel_id
        self.raw = raw
        return self

    def to_json(self):
        return {
            'scid': "{}x{}x{}".format(self.scid >> 40, self.scid >> 16 & 0xFFFFFF, self.scid & 0xFFFF),
            'nscid': self.scid,
            'raw': hexlify(self.raw).decode('ASCII'),
        }


class NodeAnnouncement(Base):
    __tablename__ = "node_announcements"
    node_id = Column(BLOB, primary_key=True)
    timestamp = Column(DateTime, primary_key=True)
    raw = Column(BLOB)

    @classmethod
    def from_gossip(cls, gna: parser.NodeAnnouncement,
                    raw: bytes) -> 'NodeAnnouncement':
        assert(raw[:2] == b'\x01\x01')
        self = NodeAnnouncement()
        self.node_id = gna.node_id
        self.timestamp = datetime.fromtimestamp(gna.timestamp)
        self.raw = raw
        return self

    def to_json(self):
        return {
            'node_id': hexlify(self.node_id).decode('ASCII'),
            'timestamp': self.timestamp.strftime("%Y/%m/%d, %H:%M:%S"),
            'raw': hexlify(self.raw).decode('ASCII'),
        }
