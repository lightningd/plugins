#!/usr/bin/env python3
"""Plugin that probes the network for failed channels.

This plugin regularly performs a random probe of the network by sending a
payment to a random node in the network, with a random `payment_hash`, and
observing how the network reacts. The random `payment_hash` results in the
payments being rejected at the destination, so no funds are actually
transferred. The error messages however allow us to gather some information
about the success probability of a payment, and the stability of the channels.

The random selection of destination nodes is a worst case scenario, since it's
likely that most of the nodes in the network are leaf nodes that are not
well-connected and often offline at any point in time. Expect to see a lot of
errors about being unable to route these payments as a result of this.

The probe data is stored in a sqlite3 database for later inspection and to be
able to eventually draw pretty plots about how the network stability changes
over time. For now you can inspect the results using the `sqlite3` command
line utility:

```bash
sqlite3  ~/.lightning/probes.db "select destination, erring_channel, failcode from probes"
```

Failcode -1 and 16399 are special:

 - -1 indicates that we were unable to find a route to the destination. This
    usually indicates that this is a leaf node that is currently offline.

 - 16399 is the code for unknown payment details and indicates a successful
   probe. The destination received the incoming payment but could not find a
   matching `payment_key`, which is expected since we generated the
   `payment_hash` at random :-)

"""
from datetime import datetime
from lightning import Plugin, RpcError
from random import choice
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from time import sleep, time
import heapq
import json
import os
import random
import string
import threading


Base = declarative_base()
plugin = Plugin()

exclusions = []
temporary_exclusions = {}


class Probe(Base):
    __tablename__ = "probes"
    id = Column(Integer, primary_key=True)
    destination = Column(String)
    route = Column(String)
    error = Column(String)
    erring_channel = Column(String)
    failcode = Column(Integer)
    payment_hash = Column(String)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)


def start_probe(plugin):
    t = threading.Thread(target=probe, args=[plugin])
    t.daemon = True
    t.start()


@plugin.method('probe')
def probe(plugin):
    nodes = plugin.rpc.listnodes()['nodes']
    dst = choice(nodes)

    s = plugin.Session()
    p = Probe(destination=dst['nodeid'], started_at=datetime.now())
    s.add(p)
    try:
        route = plugin.rpc.getroute(
            dst['nodeid'],
            msatoshi=10000,
            riskfactor=1,
            exclude=exclusions + list(temporary_exclusions.keys())
        )['route']
        p.route = ','.join([r['channel'] for r in route])
        p.payment_hash = ''.join(choice(string.hexdigits) for _ in range(64))
    except RpcError:
        p.failcode = -1
        s.commit()
        return
    s.commit()

    try:
        plugin.rpc.sendpay(route, p.payment_hash)
        plugin.rpc.waitsendpay(p.payment_hash)
    except RpcError as e:
        error = e.error['data']
        p.erring_channel = e.error['data']['erring_channel']
        p.failcode = e.error['data']['failcode']
        p.error = json.dumps(error)

    if p.failcode in [16392, 16394]:
        exclusion = "{erring_channel}/{erring_direction}".format(**error)
        print('Adding exclusion for channel {} ({} total))'.format(
            exclusion, len(exclusions))
        )
        exclusions.append(exclusion)

    if p.failcode == 4103:
        exclusion = "{erring_channel}/{erring_direction}".format(**error)
        print('Adding temporary exclusion for channel {} ({} total))'.format(
            exclusion, len(temporary_exclusions))
        )
        expiry = time() + plugin.probe_exclusion_duration
        temporary_exclusions[exclusion] = expiry

    p.finished_at = datetime.now()
    s.commit()
    s.close()


def clear_temporary_exclusion(plugin):
    timed_out = [k for k, v in temporary_exclusions.items() if v < time()]
    for k in timed_out:
        del temporary_exclusions[k]

    print("Removed {}/{} temporary exclusions.".format(
        len(timed_out), len(temporary_exclusions))
    )


def schedule(plugin):
    # List of scheduled calls with next runtime, function and interval
    next_runs = [
        (time() + 300, clear_temporary_exclusion, 300),
        (time() + plugin.probe_interval, start_probe, plugin.probe_interval)
    ]
    heapq.heapify(next_runs)

    while True:
        n = heapq.heappop(next_runs)
        t = n[0] - time()
        if t > 0:
            sleep(t)
        # Call the function
        n[1](plugin)

        # Schedule the next run
        heapq.heappush(next_runs, (time() + n[2], n[1], n[2]))


@plugin.init()
def init(configuration, options, plugin):
    plugin.probe_interval = int(options['probe-interval'])
    plugin.probe_exclusion_duration = int(options['probe-exclusion-duration'])

    db_filename = 'sqlite:///' + os.path.join(
        configuration['lightning-dir'],
        'probes.db'
    )

    engine = create_engine(db_filename, echo=True)
    Base.metadata.create_all(engine)
    plugin.Session = sessionmaker()
    plugin.Session.configure(bind=engine)
    t = threading.Thread(target=schedule, args=[plugin])
    t.daemon = True
    t.start()


plugin.add_option(
    'probe-interval',
    '3600',
    'How many seconds should we wait between probes?'
)
plugin.add_option(
    'probe-exclusion-duration',
    '1800',
    'How many seconds should temporarily failed channels be excluded?'
)
plugin.run()
