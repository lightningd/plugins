#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.9.2"
# dependencies = [
#   "pyln-client>=24.11",
#   "portalocker>=3.2,<4",
# ]
# ///

import sys
import time
import json
import socket
import os
import base64

import urllib
import urllib.request
import urllib.error
from art import sauron_eye
from pyln.client import Plugin
import portalocker

from ratelimit import GlobalRateLimiter
from shared_cache import SharedRequestCache


plugin = Plugin(dynamic=False)
plugin.sauron_socks_proxies = None
plugin.sauron_network = "test"


class SauronError(Exception):
    pass


original_getaddrinfo = socket.getaddrinfo

# def ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
#     return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

# @contextmanager
# def force_ipv4():
#     socket.getaddrinfo = ipv4_only_getaddrinfo
#     try:
#         yield
#     finally:
#         socket.getaddrinfo = original_getaddrinfo

rate_limiter = GlobalRateLimiter(rate_per_second=1, max_wait_seconds=15)
cache = SharedRequestCache(ttl_seconds=30)


def fetch(plugin, url):
    """Fetch this {url}, maybe through a pre-defined proxy."""

    # FIXME: Maybe try to be smart and renew circuit to broadcast different
    # transactions ? Hint: lightningd will agressively send us the same
    # transaction a certain amount of times.
    class SimpleResponse:
        def __init__(self, content, status_code, headers):
            self.content = content
            self.status_code = status_code
            self.headers = headers
            try:
                self.text = content.decode("utf-8")
            except:
                self.text = str(content)

        def json(self):
            return json.loads(self.text)

    key = cache.make_key(url, body="fetch")
    lock_file = f"/tmp/fetch_lock_{key}.lock"

    # Fast path
    plugin.log(f"Checking cache for {url}", level="debug")
    cached = cache.get(key)
    if cached:
        plugin.log(f"Cache hit for {url}", level="debug")
        return SimpleResponse(
            base64.b64decode(cached["content_b64"]), cached["status"], cached["headers"]
        )

    # Lock per URL
    os.makedirs("/tmp", exist_ok=True)

    max_retries = 10
    backoff_factor = 1
    status_forcelist = [429, 500, 502, 503, 504]

    for attempt in range(max_retries + 1):
        try:
            plugin.log(f"Getting fetch lock for {url}", level="debug")
            with portalocker.Lock(lock_file, timeout=20):
                # Inside lock, re-check cache
                plugin.log(f"Re-checking cache for {url}", level="debug")
                cached = cache.get(key)
                if cached:
                    plugin.log(f"Cache hit for {url}", level="debug")
                    return SimpleResponse(
                        base64.b64decode(cached["content_b64"]),
                        cached["status"],
                        cached["headers"],
                    )

                plugin.log("Waiting for rate limit", level="debug")
                rate_limiter.acquire()
                plugin.log("Rate limit acquired", level="debug")

                start = time.time()
                plugin.log(f"Opening URL: {url}", level="debug")

                # Resolve the host manually to see what address it's using
                # host = urllib.parse.urlparse(url).hostname
                # port = urllib.parse.urlparse(url).port or 443
                # addr_info = socket.getaddrinfo(host, port)
                # for family, type, proto, canonname, sockaddr in addr_info[
                #     :3
                # ]:  # Show first few
                #     plugin.log(
                #         f"Resolved {host}:{port} -> {sockaddr[0]} (family: {'IPv4' if family == socket.AF_INET else 'IPv6' if family == socket.AF_INET6 else family})",
                #         level="debug",
                #     )
                with urllib.request.urlopen(url, timeout=3) as response:
                    elapsed = time.time() - start
                    plugin.log(f"Request took {elapsed:.3f}s", level="debug")

                    data = response.read()
                    status = response.status
                    headers = dict(response.headers)

                    result = SimpleResponse(data, status, headers)

                    cache.set(
                        key,
                        {
                            "status": status,
                            "headers": headers,
                            "content_b64": base64.b64encode(result.content).decode(
                                "ascii"
                            ),
                        },
                    )
                    return result

        except portalocker.exceptions.LockException:
            plugin.log(f"Timeout waiting for request lock for {url}")
            time.sleep(0.5)
            continue

        except urllib.error.HTTPError as e:
            # HTTP error responses (4xx, 5xx)
            plugin.log(f"HTTP {e.code} for {url}", level="debug")
            data = e.read() if e.fp else b""
            headers = dict(e.headers) if e.headers else {}

            # Retry on specific status codes
            if e.code in status_forcelist and attempt < max_retries:
                wait_time = backoff_factor * (2**attempt)
                plugin.log(
                    f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})",
                    level="debug",
                )
                time.sleep(wait_time)
                continue

            # Return error response (don't raise)
            return SimpleResponse(data, e.code, headers)

        except (urllib.error.URLError, OSError, ConnectionError) as e:
            # Network errors (DNS, connection refused, timeout, etc.)
            if attempt < max_retries:
                wait_time = backoff_factor * (2**attempt)
                plugin.log(
                    f"Network error, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries}): {e}",
                    level="debug",
                )
                time.sleep(wait_time)
                continue
            else:
                plugin.log(f"Failed after {max_retries} retries: {e}", level="error")
                raise

        except Exception as e:
            plugin.log(f"Failed: {e}", level="error")
            raise


@plugin.init()
def init(plugin, options, **kwargs):
    plugin.api_endpoint = options.get("sauron-api-endpoint", None)
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

    api = "mempool.space" if "mutinynet.com" in plugin.api_endpoint else "Esplora"
    plugin.log(f"Sauron plugin initialized using {api} API")
    plugin.log(sauron_eye)


@plugin.method("getchaininfo")
def getchaininfo(plugin, **kwargs):
    blockhash_url = "{}/block-height/0".format(plugin.api_endpoint)
    blockcount_url = "{}/blocks/tip/height".format(plugin.api_endpoint)
    chains = {
        "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f": "main",
        "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943": "test",
        "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206": "regtest",
        "00000008819873e925422c1ff0f99f7cc9bbb232af63a077a480a3633bee1ef6": "signet",
    }

    genesis_req = fetch(plugin, blockhash_url)
    if not genesis_req.status_code == 200:
        raise SauronError(
            "Endpoint at {} returned {} ({}) when trying to "
            "get genesis block hash.".format(
                blockhash_url, genesis_req.status_code, genesis_req.text
            )
        )

    blockcount_req = fetch(plugin, blockcount_url)
    if not blockcount_req.status_code == 200:
        raise SauronError(
            "Endpoint at {} returned {} ({}) when trying to get blockcount.".format(
                blockcount_url, blockcount_req.status_code, blockcount_req.text
            )
        )
    if genesis_req.text not in chains.keys():
        raise SauronError("Unsupported network")
    plugin.sauron_network = chains[genesis_req.text]

    # We wouldn't be able to hit it if its bitcoind wasn't synced, so
    # ibd = false and headercount = blockcount
    return {
        "chain": plugin.sauron_network,
        "blockcount": blockcount_req.text,
        "headercount": blockcount_req.text,
        "ibd": False,
    }


@plugin.method("getrawblockbyheight")
def getrawblock(plugin, height, **kwargs):
    blockhash_url = "{}/block-height/{}".format(plugin.api_endpoint, height)
    blockhash_req = fetch(plugin, blockhash_url)
    if blockhash_req.status_code != 200:
        return {
            "blockhash": None,
            "block": None,
        }

    block_url = "{}/block/{}/raw".format(plugin.api_endpoint, blockhash_req.text)
    while True:
        block_req = fetch(plugin, block_url)
        if block_req.status_code != 200:
            return {
                "blockhash": None,
                "block": None,
            }
        # We may download partial/incomplete files for Esplora. Best effort to
        # not crash lightningd by sending an invalid (trimmed) block.
        # NOTE: this will eventually be fixed upstream, at which point we should
        # just reuse the retry handler.
        content_len = block_req.headers.get("Content-length")
        if content_len is None:
            break
        if int(content_len) == len(block_req.content):
            break
        plugin.log("Esplora gave us an incomplete block, retrying in 2s", level="error")
        time.sleep(2)

    return {
        "blockhash": blockhash_req.text,
        "block": block_req.content.hex(),
    }


@plugin.method("sendrawtransaction")
def sendrawtx(plugin, tx, **kwargs):
    sendtx_url = "{}/tx".format(plugin.api_endpoint)

    try:
        req = urllib.request.Request(
            sendtx_url, data=tx.encode() if isinstance(tx, str) else tx, method="POST"
        )

        with urllib.request.urlopen(req, timeout=10) as _response:
            return {
                "success": True,
                "errmsg": "",
            }

    except Exception as e:
        return {
            "success": False,
            "errmsg": str(e),
        }


@plugin.method("getutxout")
def getutxout(plugin, txid, vout, **kwargs):
    gettx_url = "{}/tx/{}".format(plugin.api_endpoint, txid)
    status_url = "{}/tx/{}/outspend/{}".format(plugin.api_endpoint, txid, vout)

    gettx_req = fetch(plugin, gettx_url)
    if not gettx_req.status_code == 200:
        raise SauronError(
            "Endpoint at {} returned {} ({}) when trying to get transaction.".format(
                gettx_url, gettx_req.status_code, gettx_req.text
            )
        )
    status_req = fetch(plugin, status_url)
    if not status_req.status_code == 200:
        raise SauronError(
            "Endpoint at {} returned {} ({}) when trying to get utxo status.".format(
                status_url, status_req.status_code, status_req.text
            )
        )

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
def estimatefees(plugin, **kwargs):
    feerate_url = "{}/fee-estimates".format(plugin.api_endpoint)

    feerate_req = fetch(plugin, feerate_url)
    assert feerate_req.status_code == 200
    feerates = feerate_req.json()
    if plugin.sauron_network in ["test", "signet"]:
        # FIXME: remove the hack if the test API is "fixed"
        feerate = feerates.get("144", 1)
        slow = normal = urgent = very_urgent = int(feerate * 10**3)
    else:
        # It returns sat/vB, we want sat/kVB, so multiply everything by 10**3
        slow = int(feerates["144"] * 10**3)
        normal = int(feerates["12"] * 10**3)
        urgent = int(feerates["6"] * 10**3)
        very_urgent = int(feerates["2"] * 10**3)

    feerate_floor = int(feerates.get("1008", slow) * 10**3)
    feerates = [
        {"blocks": 2, "feerate": very_urgent},
        {"blocks": 6, "feerate": urgent},
        {"blocks": 12, "feerate": normal},
        {"blocks": 144, "feerate": slow},
    ]

    return {
        "opening": normal,
        "mutual_close": normal,
        "unilateral_close": very_urgent,
        "delayed_to_us": normal,
        "htlc_resolution": urgent,
        "penalty": urgent,
        "min_acceptable": slow // 2,
        "max_acceptable": very_urgent * 10,
        "feerate_floor": feerate_floor,
        "feerates": feerates,
    }


plugin.add_option(
    "sauron-api-endpoint",
    "",
    "The URL of the esplora or mempool.space instance to hit (including '/api').",
)

plugin.add_option(
    "sauron-tor-proxy",
    "",
    "Tor's SocksPort address in the form address:port, don't specify the"
    " protocol.  If you didn't modify your torrc you want to put"
    " 'localhost:9050' here.",
)


plugin.run()
