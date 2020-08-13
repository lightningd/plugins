#!/usr/bin/env python3
import sys
import requests

from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from art import sauron_eye
from pyln.client import Plugin


plugin = Plugin(dynamic=False)
plugin.sauron_socks_proxies = None


class SauronError(Exception):
    pass


def fetch(url):
    """Fetch this {url}, maybe through a pre-defined proxy."""
    # FIXME: Maybe try to be smart and renew circuit to broadcast different
    # transactions ? Hint: lightningd will agressively send us the same
    # transaction a certain amount of times.
    session = requests.session()
    session.proxies = plugin.sauron_socks_proxies
    retry_strategy = Retry(
        backoff_factor=1,
        total=10,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session.get(url)


@plugin.init()
def init(plugin, options, configuration, **kwargs):
    plugin.api_endpoint = options["sauron-api-endpoint"]
    if not plugin.api_endpoint:
        raise SauronError("You need to specify the sauron-api-endpoint option.")
        sys.exit(1)

    if options["sauron-tor-proxy"]:
        address, port = options["sauron-tor-proxy"].split(":")
        socks5_proxy = "socks5h://{}:{}".format(address, port)
        plugin.sauron_socks_proxies = {
            "http": socks5_proxy,
            "https": socks5_proxy,
        }
        plugin.log("Using proxy {} for requests".format(socks5_proxy))

    plugin.log("Sauron plugin initialized")
    plugin.log(sauron_eye)


@plugin.method("getchaininfo")
def getchaininfo(plugin, **kwargs):
    blockhash_url = "{}/block-height/0".format(plugin.api_endpoint)
    blockcount_url = "{}/blocks/tip/height".format(plugin.api_endpoint)
    chains = {
        "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f":
        "main",
        "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943":
        "test",
        "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206":
        "regtest"
    }

    genesis_req = fetch(blockhash_url)
    if not genesis_req.status_code == 200:
        raise SauronError("Endpoint at {} returned {} ({}) when trying to "
                          "get genesis block hash."
                          .format(blockhash_url, genesis_req.status_code,
                                  genesis_req.text))

    blockcount_req = fetch(blockcount_url)
    if not blockcount_req.status_code == 200:
        raise SauronError("Endpoint at {} returned {} ({}) when trying to "
                          "get blockcount.".format(blockcount_url,
                                                   blockcount_req.status_code,
                                                   blockcount_req.text))
    if genesis_req.text not in chains.keys():
        raise SauronError("Unsupported network")

    # We wouldn't be able to hit it if its bitcoind wasn't synced, so
    # ibd = false and headercount = blockcount
    return {
        "chain": chains[genesis_req.text],
        "blockcount": blockcount_req.text,
        "headercount": blockcount_req.text,
        "ibd": False,
    }


@plugin.method("getrawblockbyheight")
def getrawblock(plugin, height, **kwargs):
    blockhash_url = "{}/block-height/{}".format(plugin.api_endpoint, height)

    blockhash_req = fetch(blockhash_url)
    block_req = fetch("{}/block/{}/raw".format(plugin.api_endpoint,
                                                     blockhash_req.text))
    if blockhash_req.status_code != 200 or block_req.status_code != 200:
        return {
            "blockhash": None,
            "block": None,
        }

    return {
        "blockhash": blockhash_req.text,
        "block": block_req.content.hex(),
    }


@plugin.method("sendrawtransaction")
def sendrawtx(plugin, tx, **kwargs):
    sendtx_url = "{}/tx".format(plugin.api_endpoint)

    sendtx_req = requests.post(sendtx_url, data=tx)
    if sendtx_req.status_code != 200:
        return {
            "success": False,
            "errmsg": sendtx_req.text,
        }

    return {
        "success": True,
        "errmsg": "",
    }


@plugin.method("getutxout")
def getutxout(plugin, txid, vout, **kwargs):
    gettx_url = "{}/tx/{}".format(plugin.api_endpoint, txid)
    status_url = "{}/tx/{}/outspend/{}".format(plugin.api_endpoint, txid, vout)

    gettx_req = fetch(gettx_url)
    if not gettx_req.status_code == 200:
        raise SauronError("Endpoint at {} returned {} ({}) when trying to "
                          "get transaction.".format(gettx_url,
                                                    gettx_req.status_code,
                                                    gettx_req.text))
    status_req = fetch(status_url)
    if not status_req.status_code == 200:
        raise SauronError("Endpoint at {} returned {} ({}) when trying to "
                          "get utxo status.".format(status_url,
                                                    status_req.status_code,
                                                    status_req.text))

    if status_req.json()["spent"]:
        return {
            "amount": None,
            "script": None,
        }

    txo = gettx_req.json()["vout"][vout]
    return {
        "amount": txo["value"],
        "script": txo["scriptpubkey"],
    }


@plugin.method("estimatefees")
def getfeerate(plugin, **kwargs):
    feerate_url = "{}/fee-estimates".format(plugin.api_endpoint)

    feerate_req = fetch(feerate_url)
    assert feerate_req.status_code == 200
    feerates = feerate_req.json()
    # It renders sat/vB, we want sat/kVB, so multiply everything by 10**3
    slow = int(feerates["144"] * 10**3)
    normal = int(feerates["5"] * 10**3)
    urgent = int(feerates["3"] * 10**3)
    very_urgent = int(feerates["2"] * 10**3)

    return {
        "opening": normal,
        "mutual_close": normal,
        "unilateral_close": very_urgent,
        "delayed_to_us": normal,
        "htlc_resolution": urgent,
        "penalty": urgent,
        "min_acceptable": slow // 2,
        "max_acceptable": very_urgent * 10,
    }


plugin.add_option(
    "sauron-api-endpoint",
    "",
    "The URL of the esplora instance to hit (including '/api')."
)

plugin.add_option(
    "sauron-tor-proxy",
    "",
    "Tor's SocksPort address in the form address:port, don't specify the"
    " protocol.  If you didn't modify your torrc you want to put"
    "'localhost:9050' here."
)


plugin.run()
