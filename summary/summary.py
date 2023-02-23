#!/usr/bin/env python3
from pyln.client import Plugin, Millisatoshi
from packaging import version
from collections import namedtuple
from operator import attrgetter
from summary_avail import trace_availability, addpeer
import pyln.client
import requests
import threading
import time
import pickle
import sys


plugin = Plugin(autopatch=True)
datastore_key = ['summary', 'avail']

Channel = namedtuple('Channel', ['total', 'ours', 'theirs', 'pid', 'private', 'connected', 'scid', 'avail', 'base', 'ppm'])
Charset = namedtuple('Charset', ['double_left', 'left', 'bar', 'mid', 'right', 'double_right', 'empty'])
draw_boxch = Charset('╟', '├', '─', '┼', '┤', '╢', '║')
draw_ascii = Charset('#', '[', '-', '+', ']', '#', '|')

summary_description = "Gets summary information about this node.\n"\
                      "Pass a list of scids to the {exclude} parameter to exclude some channels from the outputs.\n"\
                      "Sort the result by using the {sortkey} parameter that can be one of 'total', 'ours', 'theirs', 'scid' (default), 'avail', 'base', 'ppm'."


class PeerThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True

    def run(self):
        # delay initial execution, so peers have a chance to connect on startup
        time.sleep(plugin.avail_interval)

        while True:
            try:
                rpcpeers = plugin.rpc.listpeers()
                trace_availability(plugin, rpcpeers)
                write_datastore(plugin)
                plugin.log("[PeerThread] Peerstate wrote to datastore. "
                           "Sleeping now...", 'debug')
                time.sleep(plugin.avail_interval)
            except Exception as ex:
                plugin.log("[PeerThread] " + str(ex), 'warn')


class PriceThread(threading.Thread):
    def __init__(self, proxies):
        super().__init__()
        self.daemon = True
        self.proxies = proxies

    def run(self):
        while True:
            try:
                # NOTE: Bitstamp has a DNS/Proxy issues that can return 404
                # Workaround: retry up to 5 times with a delay
                for _ in range(5):
                    r = requests.get('https://www.bitstamp.net/api/v2/ticker/btc{}'.format(plugin.currency.lower()), proxies=self.proxies)
                    if not r.status_code == 200:
                        time.sleep(1)
                        continue
                    break
                plugin.fiat_per_btc = float(r.json()['last'])
            except Exception as ex:
                plugin.log("[PriceThread] " + str(ex), 'warn')
            # Six hours is more than often enough for polling
            time.sleep(6 * 3600)


def to_fiatstr(msat: Millisatoshi):
    return "{}{:.2f}".format(plugin.currency_prefix,
                             int(msat) / 10**11 * plugin.fiat_per_btc)


# appends an output table header that explains fields and capacity
def append_header(table, max_msat):
    short_str = Millisatoshi(max_msat).to_approx_str()
    draw = plugin.draw
    table.append("%c%-13sOUT/OURS %c IN/THEIRS%12s%c SCID           FLAG  BASE   PPM AVAIL  ALIAS"
                 % (draw.left, short_str, draw.mid, short_str, draw.right))


@plugin.method("summary", long_desc=summary_description)
def summary(plugin, exclude='', sortkey=None, ascii=None):
    """Gets summary information about this node."""

    # Sets ascii mode for this and future requests (if requested)
    if ascii is not None:
        if ascii:
            plugin.draw = draw_ascii
        else:
            plugin.draw = draw_boxch

    reply = {}
    info = plugin.rpc.getinfo()
    funds = plugin.rpc.listfunds()
    peers = plugin.rpc.listpeers()['peers']

    # Make it stand out if we're not on mainnet.
    if info['network'] != 'bitcoin':
        reply['network'] = info['network'].upper()

    if hasattr(plugin, 'my_address') and plugin.my_address:
        reply['my_address'] = plugin.my_address
    else:
        reply['warning_no_address'] = "NO PUBLIC ADDRESSES"

    utxos = [int(f['amount_msat']) for f in funds['outputs']
             if f['status'] == 'confirmed']
    reply['num_utxos'] = len(utxos)
    utxo_amount = Millisatoshi(sum(utxos))
    reply['utxo_amount'] = utxo_amount.to_btc_str()

    avail_out = Millisatoshi(0)
    avail_in = Millisatoshi(0)
    chans = []
    reply['num_channels'] = 0
    reply['num_connected'] = 0
    reply['num_gossipers'] = 0
    for p in peers:
        pid = p['id']
        channels = []
        if 'channels' in p:
            channels = p['channels']
        elif 'num_channels' in p and p['num_channels'] > 0:
            channels = plugin.rpc.listpeerchannels(pid)['channels']
        addpeer(plugin, p)
        active_channel = False
        for c in channels:
            if c['state'] != 'CHANNELD_NORMAL':
                continue
            active_channel = True
            if c['short_channel_id'] in exclude:
                continue
            if p['connected']:
                reply['num_connected'] += 1
            if c['our_reserve_msat'] < c['to_us_msat']:
                to_us = c['to_us_msat'] - c['our_reserve_msat']
            else:
                to_us = Millisatoshi(0)
            avail_out += to_us

            # We have to derive amount to them
            to_them = c['total_msat'] - c['to_us_msat']
            if c['their_reserve_msat'] < to_them:
                to_them = to_them - c['their_reserve_msat']
            else:
                to_them = Millisatoshi(0)
            avail_in += to_them
            reply['num_channels'] += 1
            chans.append(Channel(
                c['total_msat'],
                to_us, to_them,
                pid,
                c['private'],
                p['connected'],
                c['short_channel_id'],
                plugin.persist['p'][pid]['a'],
                Millisatoshi(c['fee_base_msat']),
                c['fee_proportional_millionths'],
            ))

        if not active_channel and p['connected']:
            reply['num_gossipers'] += 1

    reply['avail_out'] = avail_out.to_btc_str()
    reply['avail_in'] = avail_in.to_btc_str()
    reply['fees_collected'] = Millisatoshi(info['fees_collected_msat']).to_btc_str()

    if plugin.fiat_per_btc > 0:
        reply['utxo_amount'] += ' ({})'.format(to_fiatstr(utxo_amount))
        reply['avail_out'] += ' ({})'.format(to_fiatstr(avail_out))
        reply['avail_in'] += ' ({})'.format(to_fiatstr(avail_in))
        reply['fees_collected'] += ' ({})'.format(to_fiatstr(info['fees_collected_msat']))

    if len(chans) > 0:
        if sortkey is None or sortkey.lower() not in Channel._fields:
            sortkey = plugin.sortkey
        chans = sorted(chans, key=attrgetter(sortkey.lower()))
        reply['channels_flags'] = 'P:private O:offline'
        reply['channels'] = ["\n"]
        biggest = max(max(int(c.ours), int(c.theirs)) for c in chans)
        append_header(reply['channels'], biggest)
        for c in chans:
            # Create simple line graph, 47 chars wide.
            our_len = int(round(int(c.ours) / biggest * 23))
            their_len = int(round(int(c.theirs) / biggest * 23))

            # We put midpoint in the middle.
            draw = plugin.draw
            mid = draw.mid
            if our_len == 0:
                left = "{:>23}".format('')
                mid = draw.double_left
            else:
                left = "{:>23}".format(draw.left + draw.bar * (our_len - 1))

            if their_len == 0:
                right = "{:23}".format('')
                # Both 0 is a special case.
                if our_len == 0:
                    mid = draw.empty
                else:
                    mid = draw.double_right
            else:
                right = "{:23}".format(draw.bar * (their_len - 1) + draw.right)

            s = left + mid + right

            # output short channel id, so things can be copyNpasted easily
            s += " {:14} ".format(c.scid)

            extra = ''
            if c.private:
                extra += 'P'
            else:
                extra += '_'
            if not c.connected:
                extra += 'O'
            else:
                extra += '_'
            s += '[{}] '.format(extra)

            # append fees
            s += ' {:4}'.format(c.base.millisatoshis)
            s += ' {:5}  '.format(c.ppm)

            # append 24hr availability
            s += '{:4.0%}  '.format(c.avail)

            # append alias or id
            node = plugin.rpc.listnodes(c.pid)['nodes']
            if len(node) != 0 and 'alias' in node[0]:
                s += node[0]['alias']
            else:
                s += c.pid[0:32]
            reply['channels'].append(s)

    # Make modern lightning-cli format this human-readble by default!
    reply['format-hint'] = 'simple'
    return reply


def new_datastore():
    return {'p': {}, 'r': 0, 'v': 1}  # see summary_avail.py for structure


def check_datastore(obj):
    if 'v' in obj and type(obj['v']) is int and obj['v'] == 1:
        return True
    return False


def load_datastore(plugin):
    entries = plugin.rpc.listdatastore(key=datastore_key)['datastore']
    if len(entries) == 0:
        plugin.log(f"Creating a new datastore '{datastore_key}'", 'debug')
        return new_datastore()
    persist = pickle.loads(bytearray.fromhex(entries[0]["hex"]))
    if not check_datastore(persist):
        plugin.log(f"Dismissing old datastore '{datastore_key}'", 'debug')
        return new_datastore()
    plugin.log(f"Reopened datastore '{datastore_key}' with {persist['r']} "
               f"runs and {len(persist['p'])} entries", 'debug')
    return persist


def write_datastore(plugin):
    hexstr = pickle.dumps(plugin.persist).hex()
    plugin.rpc.datastore(key=datastore_key, hex=hexstr, mode="create-or-replace")


@plugin.init()
def init(options, configuration, plugin):
    plugin.sortkey = options['summary-sortkey']
    if plugin.sortkey not in Channel._fields:
        plugin.sortkey = 'scid'  # default to 'scid' on unknown keys
    plugin.currency = options['summary-currency']
    plugin.currency_prefix = options['summary-currency-prefix']
    plugin.fiat_per_btc = 0

    plugin.avail_interval = float(options['summary-availability-interval'])
    plugin.avail_window = 60 * 60 * int(options['summary-availability-window'])
    plugin.persist = load_datastore(plugin)

    plugin.draw = draw_ascii
    # __version__ was introduced in 0.0.7.1, with utf8 passthrough support.
    if hasattr(pyln.client, "__version__") and version.parse(pyln.client.__version__) >= version.parse("0.0.7.1"):
        plugin.draw = draw_boxch
    if options.get('summary-ascii'):
        plugin.draw = draw_ascii

    info = plugin.rpc.getinfo()
    config = plugin.rpc.listconfigs()
    if 'always-use-proxy' in config and config['always-use-proxy']:
        paddr = config['proxy']
        # Default port in 9050
        if ':' not in paddr:
            paddr += ':9050'
        proxies = {'https': 'socks5h://' + paddr,
                   'http': 'socks5h://' + paddr}
    else:
        proxies = None

    # Measure availability
    PeerThread().start()
    # Try to grab conversion price
    PriceThread(proxies).start()

    # Prefer IPv4, otherwise take any to give out address.
    best_address = None
    for a in info['address']:
        if best_address is None:
            best_address = a
        elif a['type'] == 'ipv4' and best_address['type'] != 'ipv4':
            best_address = a

    if best_address:
        plugin.my_address = info['id'] + '@' + best_address['address']
        if best_address['port'] != 9735:
            plugin.my_address += ':' + str(best_address['port'])
    else:
        plugin.my_address = None

    plugin.log("Plugin summary.py initialized")


@plugin.subscribe("shutdown")
def on_rpc_command_callback(plugin, **kwargs):
    # FIXME: Writing datastore does not work on exit, as daemon is already lost.
    # plugin.log("Writing out datastore before shutting down")
    # write_datastore(plugin)
    sys.exit()


plugin.add_option(
    'summary-currency',
    'USD',
    'What currency should I look up on btcaverage?'
)
plugin.add_option(
    'summary-currency-prefix',
    'USD $',
    'What prefix to use for currency'
)
plugin.add_option(
    'summary-availability-interval',
    300,
    'How often in seconds the availability should be calculated.'
)
plugin.add_option(
    'summary-availability-window',
    72,
    'How many hours the availability should be averaged over.'
)
plugin.add_option(
    'summary-sortkey',
    'scid',
    'Sort the channels list by a namedtuple key, defaults to "scid".'
)
plugin.add_option(
    'summary-ascii',
    False,
    'If ascii mode should be enabled by default',
    'flag'
)
plugin.run()
