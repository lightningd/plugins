#!/usr/bin/env python3
import json
import requests

from art import sauron_eye
from pyln.client import Plugin


plugin = Plugin()


@plugin.init()
def init(plugin, options, configuration, **kwargs):
    plugin.api_endpoint = options.get("sauron-api-endpoint")
    if not plugin.api_endpoint:
        raise Exception("You need to specify the sauron-api-endpoint option.")

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

    genesis_req = requests.get(blockhash_url)
    blockcount_req = requests.get(blockcount_url)
    assert genesis_req.status_code == 200 and blockcount_req.status_code == 200
    if genesis_req.text not in chains.keys():
        raise Exception("Unsupported network")

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

    blockhash_req = requests.get(blockhash_url)
    # FIXME: Esplora now serves raw blocks, integrate it when deployed !
    # https://github.com/Blockstream/esplora/issues/171
    block_url = "https://blockchain.info/block/{}?format=hex"
    block_req = requests.get(block_url.format(blockhash_req.text))
    if blockhash_req.status_code != 200 or block_req.status_code != 200:
        return {
            "blockhash": None,
            "block": None,
        }

    return {
        "blockhash": blockhash_req.text,
        "block": block_req.text,
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

    gettx_req = requests.get(gettx_url)
    status_req = requests.get(status_url)
    assert gettx_req.status_code == status_req.status_code == 200
    if json.loads(status_req.text)["spent"]:
        return {
            "amount": None,
            "script": None,
        }

    txo = json.loads(gettx_req.text)["vout"][vout]
    return {
        "amount": txo["value"],
        "script": txo["scriptpubkey"],
    }


@plugin.method("estimatefees")
def getfeerate(plugin, **kwargs):
    feerate_url = "{}/fee-estimates".format(plugin.api_endpoint)

    feerate_req = requests.get(feerate_url)
    assert feerate_req.status_code == 200
    feerates = json.loads(feerate_req.text)
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

plugin.run()
