#!/usr/bin/env python3
from pyln.client import Plugin, Millisatoshi
from packaging import version
from collections import namedtuple
from summary_avail import trace_availability, addpeer
import pyln.client
import requests
import shelve
import threading
import time

plugin = Plugin(autopatch=True)

have_utf8 = False

# __version__ was introduced in 0.0.7.1, with utf8 passthrough support.
try:
    if version.parse(pyln.client.__version__) >= version.parse("0.0.7.1"):
        have_utf8 = True
except Exception:
    pass

Channel = namedtuple('Channel', ['total', 'ours', 'theirs', 'pid', 'private', 'connected', 'scid', 'avail'])
Charset = namedtuple('Charset', ['double_left', 'left', 'bar', 'mid', 'right', 'double_right', 'empty'])
if have_utf8:
    draw = Charset('╟', '├', '─', '┼', '┤', '╢', '║')
else:
    draw = Charset('#', '[', '-', '/', ']', '#', '|')

summary_description = "Gets summary information about this node.\n"\
                      "Pass a list of scids to the {exclude} parameter"\
                      " to exclude some channels from the outputs."


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
                plugin.persist.sync()
                plugin.log("[PeerThread] Peerstate availability persisted and "
                           "synced. Sleeping now...", 'debug')
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
                    r = requests.get('https://www.bitstamp.net/api/v2/ticker/BTC{}'.format(plugin.currency), proxies=self.proxies)
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
    table.append("%c%-13sOUT/OURS %c IN/THEIRS%12s%c SCID           FLAG AVAIL ALIAS"
                 % (draw.left, short_str, draw.mid, short_str, draw.right))


@plugin.method("summary", long_desc=summary_description)
def summary(plugin, exclude=''):
    """Gets summary information about this node."""

    reply = {}
    info = plugin.rpc.getinfo()
    funds = plugin.rpc.listfunds()
    peers = plugin.rpc.listpeers()

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
    for p in peers['peers']:
        pid = p['id']
        addpeer(plugin, p)
        active_channel = False
        for c in p['channels']:
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
                plugin.persist['peerstate'][pid]['avail']
            ))

        if not active_channel and p['connected']:
            reply['num_gossipers'] += 1

    reply['avail_out'] = avail_out.to_btc_str()
    reply['avail_in'] = avail_in.to_btc_str()
    reply['fees_collected'] = info['fees_collected_msat'].to_btc_str()

    if plugin.fiat_per_btc > 0:
        reply['utxo_amount'] += ' ({})'.format(to_fiatstr(utxo_amount))
        reply['avail_out'] += ' ({})'.format(to_fiatstr(avail_out))
        reply['avail_in'] += ' ({})'.format(to_fiatstr(avail_in))

    if chans != []:
        reply['channels_flags'] = 'P:private O:offline'
        reply['channels'] = ["\n"]
        biggest = max(max(int(c.ours), int(c.theirs)) for c in chans)
        append_header(reply['channels'], biggest)
        for c in chans:
            # Create simple line graph, 47 chars wide.
            our_len = int(round(int(c.ours) / biggest * 23))
            their_len = int(round(int(c.theirs) / biggest * 23))

            # We put midpoint in the middle.
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


@plugin.init()
def init(options, configuration, plugin):
    plugin.currency = options['summary-currency']
    plugin.currency_prefix = options['summary-currency-prefix']
    plugin.fiat_per_btc = 0

    plugin.avail_interval = float(options['summary-availability-interval'])
    plugin.avail_window = 60 * 60 * int(options['summary-availability-window'])
    plugin.persist = shelve.open('summary.dat', writeback=True)
    if 'peerstate' not in plugin.persist:
        plugin.log("Creating a new summary.dat shelve", 'debug')
        plugin.persist['peerstate'] = {}
        plugin.persist['availcount'] = 0
    else:
        plugin.log(f"Reopened summary.dat shelve with {plugin.persist['availcount']} "
                   f"runs and {len(plugin.persist['peerstate'])} entries", 'debug')

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
plugin.run()
