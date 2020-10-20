import click
from .common import db_session,  split_gossip
import os
from pyln.proto.primitives import varint_decode, varint_encode

@click.group()
def backup():
    pass


@backup.command()
@click.argument('destination', type=click.File('wb'))
@click.option('--db', type=str, default=None)
def create(destination, db):
    with db_session(db) as session:
        rows = session.execute("SELECT raw FROM channel_announcements")

        # Write the header now that we know we'll be writing something.
        destination.write(b"GSP\x01")

        for r in rows:
            varint_encode(len(r[0]), destination)
            destination.write(r[0])

        rows = session.execute("SELECT raw FROM channel_updates ORDER BY timestamp ASC")
        for r in rows:
            varint_encode(len(r[0]), destination)
            destination.write(r[0])

        rows = session.execute("SELECT raw FROM node_announcements ORDER BY timestamp ASC")
        for r in rows:
            varint_encode(len(r[0]), destination)
            destination.write(r[0])

        destination.close()

@backup.command()
@click.argument("source", type=click.File('rb'))
def read(source):
    """Load gossip messages from the specified source and print it to stdout

    Prints the hex-encoded raw gossip message to stdout.
    """
    header = source.read(4)
    if len(header) < 4:
        raise ValueError("Could not read header")

    tag, version = header[0:3], header[3]
    if tag != b'GSP':
        raise ValueError(f"Header mismatch, expected GSP, got {repr(tag)}")

    if version != 1:
        raise ValueError(f"Unsupported version {version}, only support up to version 1")

    for m in split_gossip(source):
        print(m.hex())
