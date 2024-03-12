#! /usr/bin/python3
import py_compile
from pyln.client import Plugin
import pyqrcode
from requests import get

plugin = Plugin()

def getChannel(peerid, chanid):
    peer = plugin.rpc.listpeers(peerid)
    assert peer, "cannot find peer"

    chan = peer["channels"]
    assert chan["channel_id"]==chanid, "cannot find channel"

    return {peer, chan}


@plugin.method("enable-spark")
def enable_spark(port = 9735):
    token = plugin.rpc.call("commando-rune")
    node_id = plugin.rpc.getinfo()["id"]
    addr = get('https://api.ipify.org').content.decode('utf8')+":"+str(port)
    res = "lnlink:" + node_id + '@' + addr + '?' + 'token=' + token["rune"]
    qr = pyqrcode.create(res, encoding="ascii")
    qr.show()
    return res

@plugin.method("_listpays")
def listpays():
    plugin.log("listpays")
    return plugin.rpc.listpays()



#-----FOLLOWING ARE NOT NEEDED??----

# @plugin.method("spark-listpeers")
# def spark_listpeers():
#     plugin.log("listpeers")
#     return plugin.rpc.listpeers()

# @plugin.method("spark-getinfo")
# def spark_getinfo():
#     plugin.log("getinfo")
#     return plugin.rpc.getinfo()

# @plugin.method("spark-offer")
# def spark_offer(amount, discription):
#     plugin.log("offer")
#     return plugin.rpc.offer(amount, discription)

# @plugin.method("spark-listfunds")
# def spark_listfunds():
#     plugin.log("listfunds")
#     return plugin.rpc.listfunds()

# @plugin.method("spark-invoice")
# def spark_invoice(amt, label, disc):
#     plugin.log("invoice")
#     return plugin.rpc.invoice(amt, label, disc)

# @plugin.method("spark-newaddr")
# def spark_invoice():
#     plugin.log("newaddr")
#     return plugin.rpc.newaddr()

# @plugin.method("spark-getlog")
# def spark_invoice():
#     plugin.log("getlog")
#     return plugin.rpc.getlog()

# --------------------




@plugin.method("_listconfigs")
def listconfigs():
    plugin.log("listconfigs")
    return plugin.rpc.listconfigs()

@plugin.method("_listinvoices")
def listconfigs(plugin):
    plugin.log("listinvoices")
    temp = plugin.rpc.listinvoices()["invoices"]
    res = []
    for i in temp:
        if i["status"]=="paid":
            res.append(i)
    return res


@plugin.method("_pay")
def pay(paystr, *args):
    pay_res = plugin.rpc.pay(paystr, args)
    return pay_res


@plugin.method("_decodecheck")
def decodecheck(paystr):
    plugin.log("decodecheck")
    s = plugin.rpc.decode(paystr)
    if(s["type"]=="bolt12 offer"):
        assert "recurrence" in s.keys(), "Offers with recurrence are unsupported"
        assert s["quantity_min"] == None or s["msatoshi"] or s["amount"], 'Offers with quantity but no payment amount are unsupported'
        assert not s["send_invoice"] or s["msatoshi"], "send_invoice offers with no amount are unsupported"
        assert not s["send_invoice"] or s["min_quantity"] == None, 'send_invoice offers with quantity are unsupported'
    return s

@plugin.method("_connectfund")
def connectfund(peeruri, satoshi, feerate):
        peerid = peeruri.split('@')[0]
        plugin.rpc.connect(peerid)
        res = plugin.rpc.fundchannel(peerid, satoshi, feerate)
        assert (res and res["channel_id"]), "cannot open channel"
        return getChannel(peerid, res["channel_id"])

plugin.method("_close")
def close(peerid, chainid, force, timeout):
        res = plugin.rpc.close(peerid, timeout)
        assert res and res["txid"], "Cannot close channel"

        peer, chan = getChannel(peerid, res["channel_id"])
        return {peer, chan, res}

@plugin.init()
def init(options, configuration, plugin):
    plugin.log("Plugin spark-commando initialized")

plugin.run()