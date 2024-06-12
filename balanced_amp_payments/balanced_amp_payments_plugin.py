#!/usr/bin/python3
"""
author: Rene Pickhardt (rene.m.pickhardt@ntnu.no)
Date: 14.1.2020
License: MIT

This plugin computes an optimal split of a payment amount for the use of AMP.
The split is optimal in the sense that it reduces the imbalance of the funds of the node.

More theory about imbalances and the algorithm to decrease the imblance of a node was
suggested by this research: https://arxiv.org/abs/1912.09555

This software is an adopted version as discussed in this post on the lightning-dev mailing
list: https://lists.linuxfoundation.org/pipermail/lightning-dev/2020-January/002418.html

It will also compute a split to receive funds over various channels with the same math
theory.

The intended use of this code ist to support a pay-plugin and the invoice command if they use AMP

A few improvements might be possible:
- Decide if amount should be rounded up / down
- filter the channels from listchannels to the ones that are currently online (check with listpeers)

=== Support: 
If you like my work consider a donation at https://patreon.com/renepickhardt or https://tallyco.in/s/lnbook
"""

from pyln.client import Plugin
import lightning
import balanced_amp_payments as bp

plugin = Plugin(autopatch=True)

amp_pay_amounts_description = "Suggests a balanced split of pay amounts to be used in AMP payments"
@plugin.method("amp_pay_amounts", long_desc=amp_pay_amounts_description)
def amp_pay_amounts(plugin, amount):
    """
    Suggests a balanced split of pay amounts to be used in AMP payments
    """
    channels = plugin.rpc.listfunds()["channels"]
    return bp.recommend_outgoing_channels(channels, amount)[0]


amp_invoice_amounts_description = "Suggests a balanced split of amounts to be used in AMP invoices"
@plugin.method("amp_invoice_amounts", long_desc=amp_invoice_amounts_description)
def amp_invoice_amounts(plugin, amount):
    """
    Suggests a balanced split of pay amounts to be used in AMP invoices
    """
    channels = plugin.rpc.listfunds()["channels"]
    return bp.recommend_incoming_channels(channels, amount)[0]


@plugin.init()
def init(options, configuration, plugin):
    #info = plugin.rpc.getinfo()
    plugin.log("Plugin balanced_payments.py initialized")


plugin.run()
