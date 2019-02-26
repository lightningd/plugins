#!/usr/bin/env python3
from lightning import Plugin, Millisatoshi
import json
import requests
import threading
import time

plugin = Plugin(autopatch=True)


class PriceThread(threading.Thread):
    def run(self):
        try:
            r = requests.get('https://apiv2.bitcoinaverage.com/convert/global'
                             '?from=BTC&to={}&amount=1'.format(plugin.currency))
            plugin.fiat_per_btc = json.loads(r.content)['price']
        except Exception:
            pass
        # Six hours is more than often enough for polling
        time.sleep(6*3600)


def to_fiatstr(msat: Millisatoshi):
    return "{}{:.2f}".format(plugin.currency_prefix,
                              int(msat) / 10**11 * plugin.fiat_per_btc)


@plugin.method("summary")
def summary(plugin):
    """Gets summary information about this node."""

    reply = {}
    info = plugin.rpc.getinfo()
    funds = plugin.rpc.listfunds()
    peers = plugin.rpc.listpeers()

    # Make it stand out if we're not on mainnet.
    if info['network'] != 'bitcoin':
        reply['network'] = info['network'].upper()

    if not plugin.my_address:
        reply['warning_no_address'] = "NO PUBLIC ADDRESSES"
    else:
        reply['my_address'] = plugin.my_address

    utxo_amount = Millisatoshi(0)
    reply['num_utxos'] = 0
    for f in funds['outputs']:
        if f['status'] != 'confirmed':
            continue
        utxo_amount += f['amount_msat']
        reply['num_utxos'] += 1
    reply['utxo_amount'] = utxo_amount.to_btc_str()

    avail_out = Millisatoshi(0)
    avail_in = Millisatoshi(0)
    chans = []
    reply['num_channels'] = 0
    reply['num_connected'] = 0
    reply['num_gossipers'] = info['num_peers']
    for p in peers['peers']:
        for c in p['channels']:
            if c['state'] != 'CHANNELD_NORMAL':
                continue
            if p['connected']:
                reply['num_connected'] += 1
                reply['num_gossipers'] -= 1
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
            chans.append((c['total_msat'], to_us, to_them, p['id'], c['private']))

    reply['avail_out'] = avail_out.to_btc_str()
    reply['avail_in'] = avail_in.to_btc_str()

    if plugin.fiat_per_btc:
        reply['utxo_amount'] += ' = ' + to_fiatstr(utxo_amount)
        reply['avail_out'] += ' = ' + to_fiatstr(avail_out)
        reply['avail_in'] += ' = ' + to_fiatstr(avail_in)

    if chans != []:
        reply['channels'] = []
        biggest = max(int(c[0]) for c in chans)
        for c in chans:
            # Create simple line graph
            s = ('-' * int((int(c[1]) / biggest * 46))
                 + '/' + '-' * int((int(c[2]) / biggest * 46)))
            # Center it
            s = "{:^47}".format(s)
            node = plugin.rpc.listnodes(c[3])['nodes']
            if len(node) != 0:
                s += ':' + node[0]['alias']
            else:
                s += ':' + c[3][0:32]
            if c[4]:
                s += ' (priv)'
            reply['channels'].append(s)

    return reply


@plugin.init()
def init(options, configuration, plugin):
    plugin.currency = options['summary-currency']
    plugin.currency_prefix = options['summary-currency-prefix']
    info = plugin.rpc.getinfo()

    # Try to grab conversion price
    PriceThread().start()

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
plugin.run()
