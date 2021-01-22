from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from contextlib import contextmanager
import os
from common import Base
import io
from pyln.proto.primitives import varint_decode
from gossipd import parse
import click
import bz2

default_db = "sqlite:///$HOME/.lightning/bitcoin/historian.sqlite3"


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


def split_gossip(reader: io.BytesIO):
    while True:
        length = varint_decode(reader)
        if length is None:
            break

        msg = reader.read(length)
        if len(msg) != length:
            raise ValueError("Incomplete read at end of file")

        yield msg


class GossipStream:
    def __init__(self, file_stream, filename, decode=True):
        self.stream = file_stream
        self.decode = decode
        self.filename = filename

        # Read header
        header = self.stream.read(4)
        assert len(header) == 4
        assert header[:3] == b"GSP"
        assert header[3] == 1

    def seek(self, offset):
        """Allow skipping to a specific point in the stream.

        The offset is denoted in bytes from the start, including the
        header, and matches the value of f.tell()
        """
        self.stream.seek(offset, io.SEEK_SET)

    def tell(self):
        """Returns the absolute position in the stream.

        Includes the header, and matches f.seek()
        """
        return self.stream.tell()

    def __iter__(self):
        return self

    def __next__(self):
        pos = self.stream.tell()
        length = varint_decode(self.stream)

        if length is None:
            raise StopIteration

        msg = self.stream.read(length)
        if len(msg) != length:
            raise ValueError(
                "Error reading snapshot at {pos}: incomplete read of {length} bytes, only got {lmsg} bytes".format(
                    pos=pos, length=length, lmsg=len(msg)
                )
            )
        if not self.decode:
            return msg

        return parse(msg)


class GossipFile(click.File):
    def __init__(self, decode=True):
        click.File.__init__(self)
        self.decode = decode

    def convert(self, value, param, ctx):
        f = bz2.open(value, "rb") if value.endswith(".bz2") else open(value, "rb")
        return GossipStream(f, value, self.decode)
