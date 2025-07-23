import click
from common import NodeAnnouncement, ChannelAnnouncement, ChannelUpdate
from tqdm import tqdm
from gossipd import parse
from cli.common import db_session, default_db


@click.group()
def db():
    pass


@db.command()
@click.argument('source', type=str)
@click.argument('destination', type=str, default=default_db)
def merge(source, destination):
    """Merge two historian databases by copying from source to destination.
    """

    meta = {
        'channel_announcements': None,
        'channel_updates': None,
        'node_announcements': None,
    }

    with db_session(source) as source, db_session(destination) as target:
        # Not strictly necessary, but I like progress indicators and ETAs.
        for table in meta.keys():
            rows = source.execute(f"SELECT count(*) FROM {table}")
            count, = rows.fetchone()
            meta[table] = count

        for r, in tqdm(
                source.execute("SELECT raw FROM channel_announcements"),
                total=meta['channel_announcements'],
        ):
            msg = parse(r)
            if isinstance(r, memoryview):
                r = bytes(r)
            target.merge(ChannelAnnouncement.from_gossip(msg, r))

        for r, in tqdm(
                source.execute("SELECT raw FROM channel_updates ORDER BY timestamp ASC"),
                total=meta['channel_updates'],
        ):
            msg = parse(r)
            if isinstance(r, memoryview):
                r = bytes(r)
            target.merge(ChannelUpdate.from_gossip(msg, r))

        for r, in tqdm(
                source.execute("SELECT raw FROM node_announcements ORDER BY timestamp ASC"),
                total=meta['node_announcements'],
        ):
            msg = parse(r)
            if isinstance(r, memoryview):
                r = bytes(r)
            target.merge(NodeAnnouncement.from_gossip(msg, r))

        target.commit()
