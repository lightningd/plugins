from binascii import hexlify
from datetime import datetime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, BigInteger, SmallInteger, DateTime, LargeBinary
import gossipd
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()


Base = declarative_base()
default_db = os.environ.get(
    "HIST_DEFAULT_DSN",
    "sqlite:///$HOME/.lightning/bitcoin/historian.sqlite3"
)


class ChannelUpdate(Base):
    __tablename__ = 'channel_updates'
    scid = Column(BigInteger, primary_key=True)
    direction = Column(SmallInteger, primary_key=True)
    timestamp = Column(DateTime, primary_key=True)
    raw = Column(LargeBinary)

    @classmethod
    def from_gossip(cls, gcu: gossipd.ChannelUpdate,
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
    raw = Column(LargeBinary)

    @classmethod
    def from_gossip(cls, gca: gossipd.ChannelAnnouncement,
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
    node_id = Column(LargeBinary, primary_key=True)
    timestamp = Column(DateTime, primary_key=True)
    raw = Column(LargeBinary)

    @classmethod
    def from_gossip(cls, gna: gossipd.NodeAnnouncement,
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


@contextmanager
def db_session(dsn):
    """Tiny contextmanager to facilitate sqlalchemy session management"""
    if dsn is None:
        dsn = default_db
    dsn = os.path.expandvars(dsn)
    engine = create_engine(dsn, echo=False)
    Base.metadata.create_all(engine)
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


def stream_snapshot_since(since, db=None):
    with db_session(db) as session:
        # Several nested queries here because join was a bit too
        # restrictive. The inner SELECT in the WHERE-clause selects all scids
        # that had any updates in the desired timerange. The outer SELECT then
        # gets all the announcements and kicks off inner SELECTs that look for
        # the latest update for each direction.
        rows = session.execute(
            """
SELECT
  a.scid,
  a.raw,
  (
    SELECT
      u.raw
    FROM
      channel_updates u
    WHERE
      u.scid = a.scid AND
      direction = 0
    ORDER BY
      timestamp
    DESC LIMIT 1
  ) as u0,
  (
    SELECT
      u.raw
    FROM
      channel_updates u
    WHERE
      u.scid = a.scid AND
      direction = 1
    ORDER BY
      timestamp
    DESC LIMIT 1
  ) as u1
FROM
  channel_announcements a
WHERE
  a.scid IN (
    SELECT
      u.scid
    FROM
      channel_updates u
    WHERE
      u.timestamp >= '{}'
    GROUP BY
      u.scid
  )
ORDER BY
  a.scid
        """.format(
                since.strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        last_scid = None
        for scid, cann, u1, u2 in rows:
            if scid == last_scid:
                continue
            last_scid = scid
            yield cann
            if u1 is not None:
                yield u1
            if u2 is not None:
                yield u2

        # Now get and return the node_announcements in the timerange. These
        # come after the channels since no node without a
        # channel_announcements and channel_update is allowed.
        rows = session.execute(
            """
SELECT
  n.node_id,
  n.timestamp,
  n.raw
FROM
  node_announcements n
WHERE
  n.timestamp >=  '{}'
GROUP BY
  n.node_id,
  n.timestamp
HAVING
  n.timestamp = MAX(n.timestamp)
ORDER BY timestamp DESC
        """.format(
                since.strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        last_nid = None
        for nid, ts, nann in rows:
            if nid == last_nid:
                continue
            last_nid = nid
            yield nann
