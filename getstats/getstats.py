#!/usr/bin/env python3

from datetime import datetime, timedelta
import os
import schedule
import sqlite3
import statistics
import time
from pyln.client import Plugin, Millisatoshi, RpcError
from threading import Thread, RLock
from typing import Union

# This plugin traces runtime statistical data. This includes:
#  - gauges are variables that change over time: num_channels, num_peers, ...
#  - events that happen: (dis)connects, htlc accepts, payments, ...
#  - counters are events with an integer value: paymment_msat, fees, ...
#
# It offers an API that can be used by plugins to make better runtime decisions:
#  Timerange queries via `getstats(name, [from], [to])`
#  median/average/min/max/sum queries via i.e. `getstats_median(name, [from], [to])`

# TODOs:
# - improve scheduler: align on time buckets
#   - no buckets that are smaller than 15m when daemon was restarted
# - make plugin.interval configurable
# - fix statistic functions when unchanged gauges have been skipped or events didnt happen
# - sample result in different OHLC timeframe candles
#   - 1hr 1day 1week 1month
# - config and methods that disables/enables various timeseries
# - advanced query API:
#   - timeserie wildcard * selection merge data
#   - liststats canonical?
#   - sum function
# - purge db method
# - limit size, remove old entries
# - trace event and hook details
# - render output method in a nice ASCII chart :D

TS_GAUGE = 1   # like a gauge, can be OHLC sampled
TS_EVENT = 2   # can be summed up and averaged sampled
TS_COUNT = 3   # like TS_EVENT but increments with custom integer values
RPC_CONTINUE = {'result': 'continue'}


plugin = Plugin()
plugin.initialized = False
plugin.dblock = RLock()
plugin.db = None
plugin.tsi = {}             # time series index cache
plugin.tst = {}             # time series type cache
plugin.sample = {}          # current sample cache
plugin._sample = {}         # last sample
plugin.interval = 15        # update interval in minutes


migrations = [
    "CREATE TABLE timeseries (id INTEGER PRIMARY KEY, name text UNIQUE, ts_type INTEGER NOT NULL)",
    "CREATE TABLE data (ts timestamp, tsi INTEGER, value INTEGER,"
    " FOREIGN KEY(tsi) REFERENCES timeseries(id)) ",
    "CREATE INDEX idx_data_id ON data (tsi)",
    "CREATE INDEX idx_data_ts ON data (ts)",
    "CREATE INDEX idx_data_idts ON data (ts, tsi)",
    "CREATE TABLE tsmask (id INTEGER PRIMARY KEY, pattern text UNIQUE)",
]


def check_initialized():
    if plugin.initialized is False:
        raise RpcError('getstats', {}, {'message': 'Plugin not yet initialized'})


def wait_initialized():
    while plugin.initialized is False:
        time.sleep(0.1)


def ensure_tsi(name: str, ts_type: int):
    """ ensures a given timeseries and type is known in the database """
    plugin.dblock.acquire()
    if name in plugin.tsi:
        plugin.dblock.release()
        return plugin.tsi[name]

    cursor = plugin.db.execute("SELECT id, ts_type from timeseries WHERE name = ? and ts_type = ?",
                               (name, ts_type))
    row = cursor.fetchone()
    if row is not None:
        plugin.tsi[name] = row[0]
        plugin.tst[name] = row[1]
        plugin.dblock.release()
        return row[0]

    plugin.db.execute("INSERT INTO timeseries (name, ts_type) VALUES (?, ?)", (name, ts_type))
    plugin.db.commit()
    cursor = plugin.db.execute("SELECT id, ts_type from timeseries WHERE name = ?", (name,))
    row = cursor.fetchone()
    plugin.tsi[name] = row[0]
    plugin.tst[name] = row[1]
    plugin.dblock.release()
    return row[0]


def get_tsi(name: str):
    """ get timeseries index either from from cache or database """
    plugin.dblock.acquire()
    if name in plugin.tsi:
        plugin.dblock.release()
        return plugin.tsi[name]
    cursor = plugin.db.execute("SELECT id, ts_type from timeseries WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row is None:
        plugin.dblock.release()
        raise ValueError(f"Unknown timeseries: {name}")
    plugin.tsi[name] = row[0]
    plugin.tst[name] = row[1]
    plugin.dblock.release()
    return row[0]


def get_tst(name: str):
    """ get timeseries type either from from cache or database """
    plugin.dblock.acquire()
    if name in plugin.tst:
        plugin.dblock.release()
        return plugin.tst[name]
    cursor = plugin.db.execute("SELECT id, ts_type from timeseries WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row is None:
        plugin.dblock.release()
        raise ValueError(f"Unknown timeseries: {name}")
    plugin.tsi[name] = row[0]
    plugin.tst[name] = row[1]
    plugin.dblock.release()
    return row[1]


def get_tstypename(value: Union[str, int]):
    if isinstance(value, str):
        value = get_tst(value)
    typename = None
    if value == TS_GAUGE:
        typename = "GAUGE"
    elif value == TS_EVENT:
        typename = "EVENT"
    elif value == TS_COUNT:
        typename = "COUNTER"
    else:
        raise ValueError(f'Unknown timeseries type: {value} {type(value)}')
    return typename


def ts_gauge(name: str, value: int):
    """ Sets a variable for the current sample """
    if plugin.initialized is False:
        return
    ensure_tsi(name, TS_GAUGE)
    if type(value) is not int:
        value = int(value)
    plugin.sample[name] = value


def ts_event(name: str):
    """ Increments an event counter within the current sample """
    if plugin.initialized is False:
        return
    ensure_tsi(name, TS_EVENT)
    plugin.sample[name] = plugin.sample.get(name, 0) + 1


def ts_count(name: str, value: int):
    """ Increments a value within the current sample """
    if plugin.initialized is False:
        return
    ensure_tsi(name, TS_COUNT)
    plugin.sample[name] = plugin.sample.get(name, 0) + value


def store_and_reset_sample():
    """ stores the current sample values """
    plugin.dblock.acquire()
    ts = datetime.now()
    for name in plugin.sample:
        value = plugin.sample[name]
        # skip recording the same gauge again and again
        if value == plugin._sample.get(name) and plugin.tst[name] == TS_GAUGE:
            continue
        plugin.db.execute("INSERT INTO data (ts, tsi, value) VALUES (?, ?, ?)",
                          (ts, get_tsi(name), value))
    plugin.db.commit()
    # Reset sample
    plugin._sample = plugin.sample
    plugin.sample = {}
    plugin.dblock.release()


def get_data(name: str, tsfrom: datetime, tsto: datetime):
    """ Returns timeseries data<ts, value> range as query cursor """
    if tsfrom is None:
        tsfrom = datetime.fromtimestamp(0)
    if tsto is None:
        tsto = datetime.now()
    if isinstance(tsfrom, str):
        tsfrom = datetime.fromisoformat(tsfrom)
    if isinstance(tsto, str):
        tsto = datetime.fromisoformat(tsto)
    plugin.dblock.acquire()
    data = plugin.db.execute("SELECT ts, value FROM data WHERE tsi = ? and ts >= ? and ts <= ?",
                             (get_tsi(name), tsfrom, tsto))
    plugin.dblock.release()
    return data


def get_values(name: str, tsfrom: datetime, tsto: datetime):
    """ Returns just the timeseries values as fetched array """
    if tsfrom is None:
        tsfrom = datetime.fromtimestamp(0)
    if tsto is None:
        tsto = datetime.now()
    if isinstance(tsfrom, str):
        tsfrom = datetime.fromisoformat(tsfrom)
    if isinstance(tsto, str):
        tsto = datetime.fromisoformat(tsto)
    plugin.dblock.acquire()
    cursor = plugin.db.execute("SELECT value FROM data WHERE tsi = ? and ts >= ? and ts <= ?",
                               (get_tsi(name), tsfrom, tsto))
    values = [value[0] for value in cursor.fetchall()]  # un-tuplify
    plugin.dblock.release()
    return values


def setup_db(plugin: Plugin):
    # open database
    plugin.dblock.acquire()
    plugin.db = sqlite3.connect('getstats.sqlite3', check_same_thread=False)

    # check or create migrations table
    result = plugin.db.execute("""
        SELECT count(name) FROM sqlite_master
        WHERE type='table' AND name='migrations'
    """)
    if not bool(result.fetchone()[0]):
        plugin.db.execute("CREATE TABLE migrations (id INTEGER PRIMARY KEY, ts timestamp)")
        plugin.db.commit()

    old_ver = plugin.db.execute("SELECT max(id) FROM migrations").fetchone()[0]
    old_ver = old_ver if old_ver is not None else 0
    if old_ver > len(migrations):
        plugin.dblock.release()
        raise Exception('Database has newer state than expected')

    # apply migrations ...
    i = 0
    for migration in migrations[old_ver:]:
        i += 1
        if type(migration) is str:
            migration = (migration, )
        if type(migration) is not tuple or len(migration) < 1 or type(migration[0]) is not str:
            plugin.dblock.release()
            raise ValueError(f'Invalid migration {i}')
        plugin.log(f'applying migration {migration}', 'debug')
        args = migration[1:]
        plugin.db.execute(migration[0], args)
        plugin.db.execute("INSERT INTO migrations (ts) VALUES (?)", (datetime.now(),))

    # read current version
    new_ver = plugin.db.execute("SELECT max(_rowid_) FROM migrations").fetchone()[0]
    plugin.log(f'database version: {new_ver} (migrated from {old_ver})')
    plugin.db.commit()
    plugin.dblock.release()


def job(plugin: Plugin):
    """ The job that collects all data """
    plugin.log('collecting stats ...', 'info')

    # partly taken from summary.py
    info = plugin.rpc.getinfo()
    funds = plugin.rpc.listfunds()
    peers = plugin.rpc.listpeers()
    forwards = plugin.rpc.listforwards()

    utxos = [int(f['amount_msat']) for f in funds['outputs'] if f['status'] == 'confirmed']
    avail_out = Millisatoshi(0)
    avail_in = Millisatoshi(0)
    num_channels = 0
    num_connected = 0
    num_gossipers = 0
    for p in peers['peers']:
        active_channel = False
        pid = p['id'][:8]

        ts_gauge(f'peer_{pid}_connected', p['connected'])
        ts_gauge(f'peer_{pid}_features', int(p.get('features', "0"), 16))

        for c in p['channels']:
            if c['state'] != 'CHANNELD_NORMAL':
                continue
            num_channels += 1
            active_channel = True
            scid = c['short_channel_id']

            ts_gauge(f'scid_{scid}_our_msat', c['to_us_msat'])
            ts_gauge(f'scid_{scid}_fee_base', c['fee_base_msat'])
            ts_gauge(f'scid_{scid}_fee_ppm', c['fee_proportional_millionths'])
            ts_gauge(f'scid_{scid}_in_payments_offered', c['in_payments_offered'])
            ts_gauge(f'scid_{scid}_in_offered_msat', c['in_offered_msat'])
            ts_gauge(f'scid_{scid}_in_payments_fulfilled', c['in_payments_fulfilled'])
            ts_gauge(f'scid_{scid}_in_fulfilled_msat', c['in_fulfilled_msat'])
            ts_gauge(f'scid_{scid}_out_payments_offered', c['out_payments_offered'])
            ts_gauge(f'scid_{scid}_out_offered_msat', c['out_offered_msat'])
            ts_gauge(f'scid_{scid}_out_payments_fulfilled', c['out_payments_fulfilled'])
            ts_gauge(f'scid_{scid}_out_fulfilled_msat', c['out_fulfilled_msat'])
            ts_gauge(f'scid_{scid}_htlcs', len(c['htlcs']))

            if p['connected']:
                num_connected += 1
            if c['our_reserve_msat'] < c['to_us_msat']:
                to_us = c['to_us_msat'] - c['our_reserve_msat']
            else:
                to_us = Millisatoshi(0)
            avail_out += to_us
            to_them = c['total_msat'] - c['to_us_msat']
            if c['their_reserve_msat'] < to_them:
                to_them = to_them - c['their_reserve_msat']
            else:
                to_them = Millisatoshi(0)
            avail_in += to_them
        if not active_channel and p['connected']:
            num_gossipers += 1

    ts_gauge('getinfo_num_peers', info['num_peers'])
    ts_gauge('getinfo_num_pending_channels', info['num_pending_channels'])
    ts_gauge('getinfo_num_active_channels', info['num_active_channels'])
    ts_gauge('getinfo_num_inactive_channels', info['num_inactive_channels'])
    ts_gauge('getinfo_fees_collected_msat', info['fees_collected_msat'])

    ts_gauge('summary_num_utxos', len(utxos))
    ts_gauge('summary_utxo_amount', Millisatoshi(sum(utxos)))
    ts_gauge('summary_num_channels', num_channels)
    ts_gauge('summary_num_connected', num_connected)
    ts_gauge('summary_num_gossipers', num_gossipers)
    ts_gauge('summary_avail_total', avail_out + avail_in)
    ts_gauge('summary_avail_out', avail_out)
    ts_gauge('summary_avail_in', avail_in)

    ts_gauge('forwards_total', len(forwards))
    # ... more on forwards: received/resolved time detla, status settled/failed

    store_and_reset_sample()


def scheduler(plugin: Plugin):
    """ Simply calls the schedule job at given interval """
    wait_initialized()
    # call once initially to make testing easier
    job(plugin)
    # reschedule at given interval
    schedule.every(plugin.interval).minutes.do(job, plugin)
    while True:
        schedule.run_pending()
        time.sleep(1)


@plugin.subscribe("channel_opened")
def on_channel_opened(plugin, channel_opened, **kwargs):
    ts_event(f"channel_opened")


@plugin.subscribe("channel_state_changed")
def on_channel_state_changed(plugin, channel_state_changed, **kwargs):
    ts_event(f"channel_state_changed")


@plugin.subscribe("connect")
def on_connect(plugin, id, address, **kwargs):
    ts_event(f"connect")


@plugin.subscribe("disconnect")
def on_disconnect(plugin, id, **kwargs):
    ts_event(f"disconnect")


@plugin.subscribe("invoice_payment")
def on_invoice_payment(plugin, invoice_payment, **kwargs):
    msat = int(Millisatoshi(invoice_payment["msat"]))
    ts_event(f"invoice_payment")
    ts_count(f"invoice_payment_msat", msat)


@plugin.subscribe("invoice_creation")
def on_invoice_creation(plugin, invoice_creation, **kwargs):
    msat = int(Millisatoshi(invoice_creation["msat"]))
    ts_event(f"invoice_creation")
    ts_count(f"invoice_creation_msat", msat)


@plugin.subscribe("warning")
def on_warning(plugin, warning, **kwargs):
    level = warning["level"]
    ts_event(f"warning")
    ts_event(f"warning_level_{level}")


@plugin.subscribe("forward_event")
def on_forward_event(plugin, forward_event, **kwargs):
    status = forward_event['status']
    in_channel = forward_event['in_channel']
    out_channel = forward_event['out_channel']
    in_msat = int(Millisatoshi(forward_event["in_msat"]))
    out_msat = int(Millisatoshi(forward_event["out_msat"]))
    fee_msat = int(Millisatoshi(forward_event['fee_msat']))
    ts_event(f"forward_event")
    ts_event(f"forward_event_status_{status}")
    ts_count(f"forward_event_status_{status}_msat", in_msat)
    ts_count(f"forward_event_status_{status}_fee", fee_msat)
    ts_event(f"forward_event_status_{status}_in_{in_channel}")
    ts_count(f"forward_event_status_{status}_in_{in_channel}_fee", fee_msat)
    ts_count(f"forward_event_status_{status}_in_{in_channel}_msat", in_msat)
    ts_event(f"forward_event_status_{status}_out_{out_channel}")
    ts_count(f"forward_event_status_{status}_out_{out_channel}_fee", fee_msat)
    ts_count(f"forward_event_status_{status}_out_{out_channel}_msat", out_msat)


@plugin.subscribe("sendpay_success")
def on_sendpay_success(plugin, sendpay_success, **kwargs):
    msat = int(Millisatoshi(sendpay_success["amount_msat"]))
    sent = int(Millisatoshi(sendpay_success["amount_sent_msat"]))
    fee = sent - msat
    ts_event(f"sendpay_success")
    ts_count(f"sendpay_success_msat", msat)
    ts_count(f"sendpay_success_fee", fee)


@plugin.subscribe("sendpay_failure")
def on_sendpay_failure(plugin, sendpay_failure, **kwargs):
    code = sendpay_failure['code']
    index = sendpay_failure['data']['erring_index']
    msat = int(Millisatoshi(sendpay_failure['data']["amount_msat"]))
    sent = int(Millisatoshi(sendpay_failure['data']["amount_sent_msat"]))
    fee = sent - msat
    ts_event(f"sendpay_failure")
    ts_event(f"sendpay_failure_code_{code}")
    ts_count(f"sendpay_failure_code_{code}_index", index)
    ts_count(f"sendpay_failure_code_{code}_msat", msat)
    ts_count(f"sendpay_failure_code_{code}_fee", fee)
    ts_count(f"sendpay_failure_index", index)
    ts_count(f"sendpay_failure_msat", msat)
    ts_count(f"sendpay_failure_fee", fee)


@plugin.subscribe("coin_movement")
def on_coin_movement(plugin, coin_movement, **kwargs):
    _type = coin_movement["type"]
    tag = coin_movement["tag"]
    credit = int(Millisatoshi(coin_movement["credit"]))
    debit = int(Millisatoshi(coin_movement["debit"]))
    ts_event(f"coin_movement")
    ts_event(f"coin_movement_type_{_type}")
    ts_event(f"coin_movement_tag_{tag}")
    ts_count(f"coin_movement_credit", credit)
    ts_count(f"coin_movement_debit", debit)
    ts_count(f"coin_movement_type_{_type}_credit", credit)
    ts_count(f"coin_movement_type_{_type}_debit", debit)
    ts_count(f"coin_movement_tag_{tag}_credit", credit)
    ts_count(f"coin_movement_tag_{tag}_debit", debit)


@plugin.subscribe("openchannel_peer_sigs")
def on_openchannel_peer_sigs(plugin, openchannel_peer_sigs, **kwargs):
    cid = openchannel_peer_sigs['channel_id'][:8]
    ts_event(f"openchannel_peer_sigs")
    ts_event(f"openchannel_peer_sigs_cid_{cid}")


@plugin.subscribe("shutdown")
def on_shutdown(plugin, **kwargs):
    plugin.dblock.acquire()
    ts_event(f"shutdown")
    # TODO: write current samples to db
    plugin.dblock.release()
    os._exit(0)  # Note: sys.exit() dows not work as intended here


# We should not go for `db_write` as it will cause troubles when we also have
# other hooks and do a lot of stuff. See ./doc/PLUGINS.md#db_write
# Bad stuff happens, even if we just start a thread and return immideately.
# @plugin.hook('db_write')
# def on_db_write(writes, data_version, plugin, **kwargs):
#     def db_write_job():
#         ts_event('db_write')
#     Thread(target=db_write_job, args=(None, )).start()
#     return RPC_CONTINUE


@plugin.hook('rpc_command')
def on_rpc_command(rpc_command, plugin, **kwargs):
    method = rpc_command['method']
    ts_event(f'rpc_command')
    ts_event(f'rpc_command_method_{method}')
    return RPC_CONTINUE


@plugin.hook('htlc_accepted')
def on_htlc_accepted(onion, htlc, plugin, **kwargs):
    msat = int(Millisatoshi(htlc['amount']))
    ts_event(f'htlc_accepted')
    ts_count(f'htlc_accepted_msat', msat)
    # TODO: onion: forward_amount ?
    return RPC_CONTINUE


@plugin.hook('commitment_revocation')
def on_commitment_revocation(commitment_txid, penalty_tx, channel_id, commitnum, plugin, **kwargs):
    # TODO: how to get in new optional arguemnts added by a new feature in a backwards compatible way??
    # def on_commitment_revocation(commitment_txid, penalty_tx, plugin, **kwargs):
    cid = channel_id[:8]
    ts_event(f'commitment_revocation')
    ts_event(f'commitment_revocatoin_cid_{cid}')
    return RPC_CONTINUE


@plugin.hook('invoice_payment')
def on_invoice_payment_hook(payment, plugin, **kwargs):
    msat = int(Millisatoshi(payment['msat']))
    ts_event(f'invoice_payment_hook')
    ts_count(f"invoice_payment_hook_msat", msat)
    return RPC_CONTINUE


@plugin.hook('openchannel')
def on_openchannel(openchannel, plugin, **kwargs):
    funding_msat = int(Millisatoshi(openchannel["funding_satoshis"]))
    ts_event(f'openchannel')
    ts_count(f'openchannel_funding_msat', funding_msat)
    return RPC_CONTINUE


@plugin.hook('custommsg')
def on_custom_msg(payload, peer_id, plugin, **kwargs):
    pid = peer_id[:8]
    ts_event(f'custommsg')
    ts_count(f'custommsg_len', len(payload))
    ts_event(f'custommsg_pid_{pid}')
    ts_count(f'custommsg_pid_{pid}_len', len(payload))
    return RPC_CONTINUE


@plugin.hook('peer_connected')
def on_peer_connected(peer, plugin, **kwargs):
    pid = peer["id"][:8]
    direction = peer["direction"]
    ts_event(f'peer_connected')
    ts_event(f'peer_connected_pid_{pid}')
    ts_event(f'peer_connected_pid_{pid}_direction_{direction}')
    return RPC_CONTINUE


@plugin.method('getstats')
def getstats(plugin: Plugin, name: str, tsfrom: str = None, tsto: str = None):
    """ Returns captured getstats timeseries data """
    check_initialized()
    plugin.dblock.acquire()
    typename = get_tstypename(name)
    rows = get_data(name, tsfrom, tsto).fetchall()

    samplesize = plugin.interval  # TODO: support custom samplesize
    _from = None
    _to = None
    result = {
        "timeseries": name,
        "type": typename,
        "samplesize": f"{samplesize} minutes",
        "from": None,
        "to": None,
        "data": {
        }
    }

    # assemble result
    for row in rows:
        ts = datetime.fromisoformat(row[0])
        # set from and to dates based on what we get from the database
        if result["from"] is None or ts < _from:
            _from = ts
            result["from"] = str(ts)
        if result["to"] is None or ts > _to:
            _to = ts
            result["to"] = str(ts)
        # set actual data
        result["data"][row[0]] = row[1]

    # append current sample from cache when queried up to now
    # should has no effect for gauges that are collected by the scheduler
    if tsto is None and name in plugin.sample:
        now = datetime.now()  # TODO: align to actual bucket
        nowstr = str(now)
        if result["from"] is None:
            result["from"] = nowstr
        if result["to"] is None or result["to"] == result["from"]:
            result["to"] = str(now + timedelta(minutes=plugin.interval))
        result["data"][nowstr] = plugin.sample.get(name, 0)

    plugin.dblock.release()
    return result


@plugin.method('getstats_median')
def getstats_median(plugin: Plugin, name: str, tsfrom: str = None, tsto: str = None):
    """ Returns the median value of a timeseries within a given timeframe """
    check_initialized()
    values = get_values(name, tsfrom, tsto)
    return statistics.median(values)


@plugin.method('getstats_average')
def getstats_average(plugin: Plugin, name: str, tsfrom: str = None, tsto: str = None):
    """ Returns the average value of a timeseries within a given timeframe """
    check_initialized()
    values = get_values(name, tsfrom, tsto)
    return statistics.mean(values)


@plugin.method('getstats_min')
def getstats_min(plugin: Plugin, name: str, tsfrom: str = None, tsto: str = None):
    """ Returns the minimal value of a timeseries within a given timeframe """
    check_initialized()
    values = get_values(name, tsfrom, tsto)
    return min(values)


@plugin.method('getstats_max')
def getstats_max(plugin: Plugin, name: str, tsfrom: str = None, tsto: str = None):
    """ Returns the maximal value of a timeseries within a given timeframe """
    check_initialized()
    values = get_values(name, tsfrom, tsto)
    return max(values)


@plugin.method('getstats_sum')
def getstats_sum(plugin: Plugin, name: str, tsfrom: str = None, tsto: str = None):
    """ Returns the sum of a timeseries within a given timeframe.
        Only works for EVENT or COUNTER not GAUGE."""
    check_initialized()
    tstype = get_tst(name)
    if tstype != TS_EVENT and tstype != TS_COUNT:
        raise ValueError(f'Invalid timeseries type to make sum: {get_tstypename(name)}')
    values = get_values(name, tsfrom, tsto)
    return sum(values)


@plugin.method('liststats')
def liststats(plugin: Plugin):
    """ Returns the names of all known getstats timeseries """
    wait_initialized()
    plugin.dblock.acquire()
    rows = plugin.db.execute("SELECT name, ts_type from timeseries ORDER BY name").fetchall()
    plugin.dblock.release()
    result = {
        "timeseries": []
    }
    for row in rows:
        result["timeseries"].append({
            "name": row[0],
            "type": get_tstypename(row[1])
        })
    return result


@plugin.method('delstats')
def delstats(plugin: Plugin, name: str, permanent: bool = True):
    """ Permanently disables or purges timeseries.

        `name` is a string that can contain wildcards to match multiple series.
        `permanent` defines wether the timeseries should not be tracked anymore.
    """
    wait_initialized()
    plugin.dblock.acquire()
    tsi = get_tsi(name)
    plugin.db.execute("DELETE FROM data WHERE tsi LIKE ?", (tsi))
    plugin.db.commit()
    plugin.dblock.release()


@plugin.init()
def init(options, configuration, plugin):
    setup_db(plugin)
    plugin.thread = Thread(target=scheduler, args=(plugin, ))
    plugin.thread.start()
    plugin.initialized = True
    plugin.log(f"Plugin {os.path.basename(__file__)} initialized")


plugin.run()
