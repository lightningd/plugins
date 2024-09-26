#!/usr/bin/env python3
try:
    import statistics
    from collections import namedtuple

    import requests
    from cachetools import TTLCache, cached
    from pyln.client import Millisatoshi, Plugin
    from requests.adapters import HTTPAdapter
    from urllib3.util import Retry
except ModuleNotFoundError as err:
    # OK, something is not installed?
    import json
    import sys

    getmanifest = json.loads(sys.stdin.readline())
    print(
        json.dumps({
            "jsonrpc": "2.0",
            "id": getmanifest["id"],
            "result": {"disable": str(err)},
        })
    )
    sys.exit(1)

plugin = Plugin()

Source = namedtuple("Source", ["name", "urlformat", "replymembers"])

sources = [
    # e.g. {"high": "18502.56", "last": "17970.41", "timestamp": "1607650787", "bid": "17961.87", "vwap": "18223.42", "volume": "7055.63066541", "low": "17815.92", "ask": "17970.41", "open": "18250.30"}
    # e.g. {"bitcoin":{"usd":17885.84}}
    Source(
        "coingecko",
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies={currency_lc}",
        ["bitcoin", "{currency_lc}"],
    ),
    # e.g. {"time":{"updated":"Dec 16, 2020 00:58:00 UTC","updatedISO":"2020-12-16T00:58:00+00:00","updateduk":"Dec 16, 2020 at 00:58 GMT"},"disclaimer":"This data was produced from the CoinDesk Bitcoin Price Index (USD). Non-USD currency data converted using hourly conversion rate from openexchangerates.org","bpi":{"USD":{"code":"USD","rate":"19,395.1400","description":"United States Dollar","rate_float":19395.14},"AUD":{"code":"AUD","rate":"25,663.5329","description":"Australian Dollar","rate_float":25663.5329}}}
    Source(
        "coindesk",
        "https://api.coindesk.com/v1/bpi/currentprice/{currency}.json",
        ["bpi", "{currency}", "rate_float"],
    ),
    # e.g. {"data":{"base":"BTC","currency":"USD","amount":"19414.63"}}
    Source(
        "coinbase",
        "https://api.coinbase.com/v2/prices/BTC-{currency}/spot",
        ["data", "amount"],
    ),
    # e.g. {  "USD" : {"15m" : 6650.3, "last" : 6650.3, "buy" : 6650.3, "sell" : 6650.3, "symbol" : "$"},  "AUD" : {"15m" : 10857.19, "last" : 10857.19, "buy" : 10857.19, "sell" : 10857.19, "symbol" : "$"},...
    Source("blockchain.info", "https://blockchain.info/ticker", ["{currency}", "last"]),
]


# Stolen from https://www.peterbe.com/plog/best-practice-with-retries-with-requests
def requests_retry_session(
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_currencyrate(plugin, currency, urlformat, replymembers):
    # NOTE: Bitstamp has a DNS/Proxy issues that can return 404
    # Workaround: retry up to 5 times with a delay
    currency_lc = currency.lower()
    url = urlformat.format(currency_lc=currency_lc, currency=currency)
    r = requests_retry_session(retries=5, status_forcelist=[404]).get(
        url, proxies=plugin.proxies
    )

    if r.status_code != 200:
        plugin.log(
            level="info", message="{}: bad response {}".format(url, r.status_code)
        )
        return None

    json = r.json()
    for m in replymembers:
        expanded = m.format(currency_lc=currency_lc, currency=currency)
        if expanded not in json:
            plugin.log(
                level="debug", message="{}: {} not in {}".format(url, expanded, json)
            )
            return None
        json = json[expanded]

    try:
        return Millisatoshi(int(10**11 / float(json)))
    except Exception:
        plugin.log(
            level="info", message="{}: could not convert {} to msat".format(url, json)
        )
        return None


def set_proxies(plugin):
    config = plugin.rpc.listconfigs()
    if "always-use-proxy" in config and config["always-use-proxy"]:
        paddr = config["proxy"]
        # Default port in 9050
        if ":" not in paddr:
            paddr += ":9050"
        plugin.proxies = {"https": "socks5h://" + paddr, "http": "socks5h://" + paddr}
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


@plugin.method("currencyrates")
def currencyrates(plugin, currency):
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

    sourceopts = options["add-source"]
    if sourceopts != [""]:
        for s in sourceopts:
            parts = s.split(",")
            sources.append(Source(parts[0], parts[1], parts[2:]))

    disableopts = options["disable-source"]
    if disableopts != [""]:
        for s in sources[:]:
            if s.name in disableopts:
                sources.remove(s)


# As a bad example: binance,https://api.binance.com/api/v3/ticker/price?symbol=BTC{currency}T,price
plugin.add_option(
    name="add-source",
    default="",
    description="Add source name,urlformat,resultmembers...",
    multi=True,
)
plugin.add_option(
    name="disable-source",
    default="",
    description="Disable source by name",
    multi=True,
)

plugin.run()
