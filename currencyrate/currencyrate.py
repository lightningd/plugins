#!/usr/bin/env python3
from pyln.client import Plugin
from collections import namedtuple
from pyln.client import Millisatoshi
from cachetools import cached, TTLCache
import requests
import statistics
import time

plugin = Plugin()

Source = namedtuple('Source', ['name', 'urlformat', 'replymembers'])

sources = [
    # e.g. {"GBP": {"volume_btc": "24.36647424", "rates": {"last": "13667.63"}, "avg_1h": "13786.86", "avg_6h": "13723.65", "avg_12h": "13680.23", "avg_24h": "13739.56"}, "USD": {"volume_btc": "27.97517017", "rates": {"last": "18204.21"}, "avg_1h": "19349.46", "avg_6h": "18621.72", "avg_12h": "18642.28", "avg_24h": "18698.94"}
    # ...
    # "GTQ": {"volume_btc": "0.03756101", "rates": {"last": "148505.46"}, "avg_1h": "148505.46", "avg_6h": "162463.69", "avg_12h": "162003.10", "avg_24h": "162003.10"}, "DKK": {"volume_btc": "0.00339923", "rates": {"last": "139737.53"}, "avg_12h": "139737.53", "avg_24h": "139737.53"}, "HTG": {"volume_btc": "0.00024758", "rates": {"last": "2019549.24"}, "avg_6h": "2019549.24", "avg_12h": "2019549.24", "avg_24h": "2019549.24"}, "NAD": {"volume_btc": "0.00722222", "rates": {"last": "360000.11"}, "avg_12h": "360000.11", "avg_24h": "360000.11"}}
    Source('localbitcoins',
           'https://localbitcoins.com/bitcoinaverage/ticker-all-currencies/',
           ['{currency}', "avg_6h"]),
    # e.g. {"high": "18502.56", "last": "17970.41", "timestamp": "1607650787", "bid": "17961.87", "vwap": "18223.42", "volume": "7055.63066541", "low": "17815.92", "ask": "17970.41", "open": "18250.30"}
    Source('bitstamp',
           'https://www.bitstamp.net/api/v2/ticker/btc{currency_lc}/',
           ['last']),
    # e.g. {"bitcoin":{"usd":17885.84}}
    Source('coingecko',
           'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies={currency_lc}',
           ['bitcoin', '{currency_lc}']),
    # e.g. {"time":{"updated":"Dec 16, 2020 00:58:00 UTC","updatedISO":"2020-12-16T00:58:00+00:00","updateduk":"Dec 16, 2020 at 00:58 GMT"},"disclaimer":"This data was produced from the CoinDesk Bitcoin Price Index (USD). Non-USD currency data converted using hourly conversion rate from openexchangerates.org","bpi":{"USD":{"code":"USD","rate":"19,395.1400","description":"United States Dollar","rate_float":19395.14},"AUD":{"code":"AUD","rate":"25,663.5329","description":"Australian Dollar","rate_float":25663.5329}}}
    Source('coindesk',
           'https://api.coindesk.com/v1/bpi/currentprice/{currency}.json',
           ['bpi', '{currency}', 'rate_float']),
    # e.g. {"data":{"base":"BTC","currency":"USD","amount":"19414.63"}}
    Source('coinbase',
           'https://api.coinbase.com/v2/prices/spot?currency={currency}',
           ['data', 'amount']),
    # e.g. {  "USD" : {"15m" : 6650.3, "last" : 6650.3, "buy" : 6650.3, "sell" : 6650.3, "symbol" : "$"},  "AUD" : {"15m" : 10857.19, "last" : 10857.19, "buy" : 10857.19, "sell" : 10857.19, "symbol" : "$"},...
    Source('blockchain.info',
           'https://blockchain.info/ticker',
           ['{currency}', 'last']),
]


def get_currencyrate(plugin, currency, req_template, response_members):
    # NOTE: Bitstamp has a DNS/Proxy issues that can return 404
    # Workaround: retry up to 5 times with a delay
    currency_lc = currency.lower()
    url = req_template.format(currency_lc=currency_lc, currency=currency)
    for _ in range(5):
        r = requests.get(url, proxies=plugin.proxies)
        if r.status_code != 200:
            time.sleep(1)
            continue
        break

    if r.status_code != 200:
        plugin.log(level='info', message='{}: bad response {}'.format(url, r.status_code))
        return None

    json = r.json()
    for m in response_members:
        expanded = m.format(currency_lc=currency_lc, currency=currency)
        if expanded not in json:
            plugin.log(level='debug', message='{}: {} not in {}'.format(url, expanded, json))
            return None
        json = json[expanded]

    try:
        return Millisatoshi(int(10**11 / float(json)))
    except Exception:
        plugin.log(level='info', message='{}: could not convert {} to msat'.format(url, json))
        return None


def set_proxies(plugin):
    config = plugin.rpc.listconfigs()
    if 'always-use-proxy' in config and config['always-use-proxy']:
        paddr = config['proxy']
        # Default port in 9050
        if ':' not in paddr:
            paddr += ':9050'
        plugin.proxies = {'https': 'socks5h://' + paddr,
                          'http': 'socks5h://' + paddr}
    else:
        plugin.proxies = None


# Don't grab these more than once per hour.                        
@cached(cache=TTLCache(maxsize=1024, ttl=3600))
def get_rates(plugin, currency):
    rates = {}
    for s in sources:
        r = get_currencyrate(plugin, currency, s.urlformat, s.replymembers)
        if r is not None:
            rates[s.name] = r

    return rates


@plugin.method("currencyrate")
def currencyrate(plugin, currency):
    """Gets currency from given APIs."""

    return get_rates(plugin, currency.upper())


@plugin.method("currencyconvert")
def currencyconvert(plugin, amount, currency):
    """Converts currency using given APIs."""
    rates = get_rates(plugin, currency.upper())
    if len(rates) == 0:
        raise Exception("No values available for currency {}".format(currency.upper()))
    val = statistics.median([m.millisatoshis for m in rates.values()]) * float(amount)
    return {"msat": Millisatoshi(round(val))}


@plugin.init()
def init(options, configuration, plugin):
    set_proxies(plugin)

    sourceopts = options['add-source']
    # Prior to 0.9.3, 'multi' was unsupported.
    if type(sourceopts) is not list:
        sourceopts = [sourceopts]
    if sourceopts != ['']:
        for s in sourceopts:
            parts = s.split(',')
            sources.append(Source(parts[0], parts[1], parts[2:]))

    disableopts = options['disable-source']
    # Prior to 0.9.3, 'multi' was unsupported.
    if type(disableopts) is not list:
        disableopts = [disableopts]
    if disableopts != ['']:
        for s in sources[:]:
            if s.name in disableopts:
                sources.remove(s)


# As a bad example: binance,https://api.binance.com/api/v3/ticker/price?symbol=BTC{currency}T,price
plugin.add_option(name='add-source', default='', description='Add source name,urlformat,resultmembers...')
plugin.add_option(name='disable-source', default='', description='Disable source by name')

# This has an effect only for recent pyln versions (0.9.3+).
plugin.options['add-source']['multi'] = True
plugin.options['disable-source']['multi'] = True

plugin.run()
