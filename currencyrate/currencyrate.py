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
    # e.g. { "Data": { "BTC-USD": { "TYPE": "266", "MARKET": "cadli", "INSTRUMENT": "BTC-USD", "CCSEQ": 612401808, "VALUE": 96353.9044445288, "VALUE_FLAG": "DOWN", "VALUE_LAST_UPDATE_TS": 1740304364, "VALUE_LAST_UPDATE_TS_NS": 843000000, "LAST_UPDATE_QUANTITY": 0.00055, "LAST_UPDATE_QUOTE_QUANTITY": 52.9805588254605, "LAST_UPDATE_VOLUME_TOP_TIER": 0.00055, "LAST_UPDATE_QUOTE_VOLUME_TOP_TIER": 52.9805588254605, "LAST_UPDATE_VOLUME_DIRECT": 0, "LAST_UPDATE_QUOTE_VOLUME_DIRECT": 0, "LAST_UPDATE_VOLUME_TOP_TIER_DIRECT": 0, "LAST_UPDATE_QUOTE_VOLUME_TOP_TIER_DIRECT": 0, "LAST_UPDATE_CCSEQ": 612459939, "CURRENT_HOUR_VOLUME": 3234.75982353854, "CURRENT_HOUR_QUOTE_VOLUME": 311782287.726718, "CURRENT_HOUR_VOLUME_TOP_TIER": 1380.775258276, "CURRENT_HOUR_QUOTE_VOLUME_TOP_TIER": 133119252.259999, "CURRENT_HOUR_VOLUME_DIRECT": 174.18057561, "CURRENT_HOUR_QUOTE_VOLUME_DIRECT": 16783315.9221611, "CURRENT_HOUR_VOLUME_TOP_TIER_DIRECT": 98.40445463, "CURRENT_HOUR_QUOTE_VOLUME_TOP_TIER_DIRECT": 9482744.45631773, "CURRENT_HOUR_OPEN": 96403.3403890657, "CURRENT_HOUR_HIGH": 96499.8344373773, "CURRENT_HOUR_LOW": 96296.2959782328, "CURRENT_HOUR_TOTAL_INDEX_UPDATES": 38522, "CURRENT_HOUR_CHANGE": -49.4359445369, "CURRENT_HOUR_CHANGE_PERCENTAGE": -0.0512803232101563, "CURRENT_DAY_VOLUME": 34542.0781712623, "CURRENT_DAY_QUOTE_VOLUME": 3332072264.07171, "CURRENT_DAY_VOLUME_TOP_TIER": 15321.9318292295, "CURRENT_DAY_QUOTE_VOLUME_TOP_TIER": 1478167872.84805, "CURRENT_DAY_VOLUME_DIRECT": 3964.12755555, "CURRENT_DAY_QUOTE_VOLUME_DIRECT": 382347567.213297, "CURRENT_DAY_VOLUME_TOP_TIER_DIRECT": 3205.51970877, "CURRENT_DAY_QUOTE_VOLUME_TOP_TIER_DIRECT": 309181884.196733, "CURRENT_DAY_OPEN": 96587.5388193773, "CURRENT_DAY_HIGH": 96691.296962515, "CURRENT_DAY_LOW": 96188.7171512824, "CURRENT_DAY_TOTAL_INDEX_UPDATES": 413875, "CURRENT_DAY_CHANGE": -233.6343748485, "CURRENT_DAY_CHANGE_PERCENTAGE": -0.241888733996428, "CURRENT_WEEK_VOLUME": 1336026.46755697, "CURRENT_WEEK_QUOTE_VOLUME": 129026278991.674, "CURRENT_WEEK_VOLUME_TOP_TIER": 763861.683146311, "CURRENT_WEEK_QUOTE_VOLUME_TOP_TIER": 73779879669.3405, "CURRENT_WEEK_VOLUME_DIRECT": 165218.28241676, "CURRENT_WEEK_QUOTE_VOLUME_DIRECT": 15940061672.59, "CURRENT_WEEK_VOLUME_TOP_TIER_DIRECT": 137725.36050851, "CURRENT_WEEK_QUOTE_VOLUME_TOP_TIER_DIRECT": 13286931484.2593, "CURRENT_WEEK_OPEN": 96157.6042409799, "CURRENT_WEEK_HIGH": 99524.81970204, "CURRENT_WEEK_LOW": 93418.0442905355, "CURRENT_WEEK_TOTAL_INDEX_UPDATES": 7945079, "CURRENT_WEEK_CHANGE": 196.3002035489, "CURRENT_WEEK_CHANGE_PERCENTAGE": 0.204144232895979, "CURRENT_MONTH_VOLUME": 5710054.43501744, "CURRENT_MONTH_QUOTE_VOLUME": 555433047724.884, "CURRENT_MONTH_VOLUME_TOP_TIER": 3345905.95729394, "CURRENT_MONTH_QUOTE_VOLUME_TOP_TIER": 325345355987.807, "CURRENT_MONTH_VOLUME_DIRECT": 828610.72203736, "CURRENT_MONTH_QUOTE_VOLUME_DIRECT": 80560037312.5898, "CURRENT_MONTH_VOLUME_TOP_TIER_DIRECT": 728267.46995616, "CURRENT_MONTH_QUOTE_VOLUME_TOP_TIER_DIRECT": 70797315423.3439, "CURRENT_MONTH_OPEN": 102459.5832836, "CURRENT_MONTH_HIGH": 102805.738542159, "CURRENT_MONTH_LOW": 91687.2854758568, "CURRENT_MONTH_TOTAL_INDEX_UPDATES": 25917283, "CURRENT_MONTH_CHANGE": -6105.6788390712, "CURRENT_MONTH_CHANGE_PERCENTAGE": -5.95910957608637, "CURRENT_YEAR_VOLUME": 15832830.137939, "CURRENT_YEAR_QUOTE_VOLUME": 1570519748700.55, "CURRENT_YEAR_VOLUME_TOP_TIER": 9338748.39398206, "CURRENT_YEAR_QUOTE_VOLUME_TOP_TIER": 926198150752.811, "CURRENT_YEAR_VOLUME_DIRECT": 2381185.60733885, "CURRENT_YEAR_QUOTE_VOLUME_DIRECT": 236283383438.395, "CURRENT_YEAR_VOLUME_TOP_TIER_DIRECT": 2094576.08364555, "CURRENT_YEAR_QUOTE_VOLUME_TOP_TIER_DIRECT": 207831698305.504, "CURRENT_YEAR_OPEN": 93441.6983892194, "CURRENT_YEAR_HIGH": 109134.786742258, "CURRENT_YEAR_LOW": 89669.6038185143, "CURRENT_YEAR_TOTAL_INDEX_UPDATES": 66561314, "CURRENT_YEAR_CHANGE": 2912.2060553094, "CURRENT_YEAR_CHANGE_PERCENTAGE": 3.1166022295303097, "MOVING_24_HOUR_VOLUME": 102516.821252946, "MOVING_24_HOUR_QUOTE_VOLUME": 9901344321.23749, "MOVING_24_HOUR_VOLUME_TOP_TIER": 47222.6107502083, "MOVING_24_HOUR_QUOTE_VOLUME_TOP_TIER": 4561341181.47015, "MOVING_24_HOUR_VOLUME_DIRECT": 12080.37485944, "MOVING_24_HOUR_QUOTE_VOLUME_DIRECT": 1166687896.03355, "MOVING_24_HOUR_VOLUME_TOP_TIER_DIRECT": 9723.55731507, "MOVING_24_HOUR_QUOTE_VOLUME_TOP_TIER_DIRECT": 939065223.413334, "MOVING_24_HOUR_OPEN": 96504.0416746479, "MOVING_24_HOUR_HIGH": 96980.8020495874, "MOVING_24_HOUR_LOW": 96188.7171512824, "MOVING_24_HOUR_TOTAL_INDEX_UPDATES": 1064171, "MOVING_24_HOUR_CHANGE": -150.1372301191, "MOVING_24_HOUR_CHANGE_PERCENTAGE": -0.15557610594722002, "MOVING_7_DAY_VOLUME": 1336026.46755697, "MOVING_7_DAY_QUOTE_VOLUME": 129026278991.674, "MOVING_7_DAY_VOLUME_TOP_TIER": 763861.683146311, "MOVING_7_DAY_QUOTE_VOLUME_TOP_TIER": 73779879669.3405, "MOVING_7_DAY_VOLUME_DIRECT": 165218.28241676, "MOVING_7_DAY_QUOTE_VOLUME_DIRECT": 15940061672.59, "MOVING_7_DAY_VOLUME_TOP_TIER_DIRECT": 137725.36050851, "MOVING_7_DAY_QUOTE_VOLUME_TOP_TIER_DIRECT": 13286931484.2593, "MOVING_7_DAY_OPEN": 96157.6042409799, "MOVING_7_DAY_HIGH": 99524.81970204, "MOVING_7_DAY_LOW": 93418.0442905355, "MOVING_7_DAY_TOTAL_INDEX_UPDATES": 7945079, "MOVING_7_DAY_CHANGE": 196.3002035489, "MOVING_7_DAY_CHANGE_PERCENTAGE": 0.204144232895979, "MOVING_30_DAY_VOLUME": 7601382.50002172, "MOVING_30_DAY_QUOTE_VOLUME": 749651057858.174, "MOVING_30_DAY_VOLUME_TOP_TIER": 4482983.31841501, "MOVING_30_DAY_QUOTE_VOLUME_TOP_TIER": 441967054248.982, "MOVING_30_DAY_VOLUME_DIRECT": 1160462.57867918, "MOVING_30_DAY_QUOTE_VOLUME_DIRECT": 114593294052.63, "MOVING_30_DAY_VOLUME_TOP_TIER_DIRECT": 1025699.36967231, "MOVING_30_DAY_QUOTE_VOLUME_TOP_TIER_DIRECT": 101295734788.519, "MOVING_30_DAY_OPEN": 104906.678715047, "MOVING_30_DAY_HIGH": 106473.551977275, "MOVING_30_DAY_LOW": 91687.2854758568, "MOVING_30_DAY_TOTAL_INDEX_UPDATES": 34829960, "MOVING_30_DAY_CHANGE": -8552.7742705182, "MOVING_30_DAY_CHANGE_PERCENTAGE": -8.15274525442722, "MOVING_90_DAY_VOLUME": 29969450.6552843, "MOVING_90_DAY_QUOTE_VOLUME": 2959084160371.88, "MOVING_90_DAY_VOLUME_TOP_TIER": 16766256.0130389, "MOVING_90_DAY_QUOTE_VOLUME_TOP_TIER": 1653651909039.25, "MOVING_90_DAY_VOLUME_DIRECT": 4373898.62146249, "MOVING_90_DAY_QUOTE_VOLUME_DIRECT": 431457527277.513, "MOVING_90_DAY_VOLUME_TOP_TIER_DIRECT": 3778684.93743527, "MOVING_90_DAY_QUOTE_VOLUME_TOP_TIER_DIRECT": 372722785015.003, "MOVING_90_DAY_OPEN": 93025.1292956724, "MOVING_90_DAY_HIGH": 109134.786742258, "MOVING_90_DAY_LOW": 89669.6038185143, "MOVING_90_DAY_TOTAL_INDEX_UPDATES": 106147246, "MOVING_90_DAY_CHANGE": 3328.7751488564, "MOVING_90_DAY_CHANGE_PERCENTAGE": 3.57836121708165, "MOVING_180_DAY_VOLUME": 61757371.8806265, "MOVING_180_DAY_QUOTE_VOLUME": 5205146815633.12, "MOVING_180_DAY_VOLUME_TOP_TIER": 34772116.8521668, "MOVING_180_DAY_QUOTE_VOLUME_TOP_TIER": 2931569122622.31, "MOVING_180_DAY_VOLUME_DIRECT": 9067126.82837174, "MOVING_180_DAY_QUOTE_VOLUME_DIRECT": 769291460006.954, "MOVING_180_DAY_VOLUME_TOP_TIER_DIRECT": 7537110.99964203, "MOVING_180_DAY_QUOTE_VOLUME_TOP_TIER_DIRECT": 644443207086.322, "MOVING_180_DAY_OPEN": 59475.8256180269, "MOVING_180_DAY_HIGH": 109134.786742258, "MOVING_180_DAY_LOW": 52646.8247969194, "MOVING_180_DAY_TOTAL_INDEX_UPDATES": 227668091, "MOVING_180_DAY_CHANGE": 36878.0788265019, "MOVING_180_DAY_CHANGE_PERCENTAGE": 62.0051566216918, "MOVING_365_DAY_VOLUME": 124813992.815458, "MOVING_365_DAY_QUOTE_VOLUME": 9251543382126.19, "MOVING_365_DAY_VOLUME_TOP_TIER": 71698918.2475569, "MOVING_365_DAY_QUOTE_VOLUME_TOP_TIER": 5304989118954.71, "MOVING_365_DAY_VOLUME_DIRECT": 16272628.0064066, "MOVING_365_DAY_QUOTE_VOLUME_DIRECT": 1230321413466.96, "MOVING_365_DAY_VOLUME_TOP_TIER_DIRECT": 13170901.775501, "MOVING_365_DAY_QUOTE_VOLUME_TOP_TIER_DIRECT": 1005107260588.58, "MOVING_365_DAY_OPEN": 51577.9542644651, "MOVING_365_DAY_HIGH": 109134.786742258, "MOVING_365_DAY_LOW": 49637.1928721595, "MOVING_365_DAY_TOTAL_INDEX_UPDATES": 484794995, "MOVING_365_DAY_CHANGE": 44775.9501800637, "MOVING_365_DAY_CHANGE_PERCENTAGE": 86.8121871419633, "LIFETIME_FIRST_UPDATE_TS": 1279408140, "LIFETIME_VOLUME": 1362359642.07922, "LIFETIME_QUOTE_VOLUME": 31884958667434.6, "LIFETIME_VOLUME_TOP_TIER": 659845523.765828, "LIFETIME_QUOTE_VOLUME_TOP_TIER": 15790397485095.4, "LIFETIME_VOLUME_DIRECT": 313936265.526703, "LIFETIME_QUOTE_VOLUME_DIRECT": 5027887123314.37, "LIFETIME_VOLUME_TOP_TIER_DIRECT": 258272547.216797, "LIFETIME_QUOTE_VOLUME_TOP_TIER_DIRECT": 3784540519413.39, "LIFETIME_OPEN": 0.04951, "LIFETIME_HIGH": 109134.786742258, "LIFETIME_HIGH_TS": 1737356171, "LIFETIME_LOW": 0.01, "LIFETIME_LOW_TS": 1286572500, "LIFETIME_TOTAL_INDEX_UPDATES": 618035860, "LIFETIME_CHANGE": 96353.8549345288, "LIFETIME_CHANGE_PERCENTAGE": 194614936.24425098 } }, "Err": {} }
    Source(
        "coindesk",
        "https://data-api.coindesk.com/index/cc/v1/latest/tick?market=cadli&instruments=BTC-{currency}&apply_mapping=true",
        ["Data", "BTC-{currency}", "VALUE"],
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
