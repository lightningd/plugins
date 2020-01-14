#!/usr/bin/python3
"""
author: Rene Pickhardt (rene.m.pickhardt@ntnu.no)
Date: 14.1.2020
License: MIT

This code computes an optimal split of a payment amount for the use of AMP.
The split is optimal in the sense that it reduces the imbalance of the funds of the node.

More theory about imbalances and the algorithm to decrease the imblance of a node was
suggested by this research: https://arxiv.org/abs/1912.09555

This software is an adopted version as discussed in this post on the lightning-dev mailing
list: https://lists.linuxfoundation.org/pipermail/lightning-dev/2020-January/002418.html

It will also compute a split to receive funds over various channels with the same math
theory.

The intended use of this code is with the pay-plugin of lighting and for the invoice API
call which ships together with this file. 

See example.py for an example how this code can be run. 

Also have a look at the plugin file

=== Support: 
If you like my work consider a donation at https://patreon.com/renepickhardt or https://tallyco.in/s/lnbook


"""

import json


def helper_computer_node_parameters(channels):
    """
    computes the total funds (\tau) and the total capacity of a node (\kappa)

    channels: is a list of local channels. Entries are formatted as in `listunfunds` API call

    returns total capacity (\kappa) and total funds (\tau) of the node as integers in satoshis.
    """
    kappa = sum(x["channel_total_sat"] for x in channels)
    tau = sum(x["channel_sat"] for x in channels)
    return kappa, tau


def helper_compute_channel_balance_coefficients(channels):
    # assign zetas to channels:
    for c in channels:
        c["zeta"] = float(c["channel_sat"]) / c["channel_total_sat"]
    return channels


def recommend_incoming_channels(channels, amount):
    assert(amount > 0), "cant receive negative amounts"

    # we need to respect the channel reserve
    total_receivable_amount = 0
    for c in channels:
        reserve = c["channel_total_sat"] / 100
        receivable_amount = max(
            0, c["channel_total_sat"] - c["channel_sat"] - reserve)
        total_receivable_amount += receivable_amount
    assert(amount <= total_receivable_amount), "can only receive %r but %r given" % (
        total_receivable_amount, amount)

    kappa, tau = helper_computer_node_parameters(channels)
    nu_target = float(tau + amount)/kappa
    channels = helper_compute_channel_balance_coefficients(channels)

    # compute rebalance amounts for channels with channel balance coefficients lower than targeted node balance coefficient
    total_rebalance_fractions = 0
    rebalance_fractions = {}
    for c in channels:
        if c["zeta"] < nu_target:
            rebalance_fraction = c["channel_total_sat"] * \
                (nu_target - c["zeta"])
            rebalance_fractions[c["short_channel_id"]] = rebalance_fraction
            total_rebalance_fractions += rebalance_fraction

    # round everything up.
    return {k: int(v * amount / total_rebalance_fractions + 0.5)for k, v in rebalance_fractions.items()}, nu_target


def recommend_outgoing_channels(channels, amount, receiving=False):
    """
    recommends how a pay amount should be split across local channels in a multipath payment scheme


    channels: is a list of local channels. Entries are formatted as in `listfunds` API call
    amount: is the amount that is supposed to be send

    Returns a dictionary of channeles with short_channel_ids as keys and recommended amounts as values.

    Since small overpayments are part of the protocol the amounts will be rounded up to the next satoshi instead of using millisatoshis
    """
    assert(amount > 0), "cant send negative amounts"

    # we need to respect the channel reserve
    total_sendable_amount = 0
    for c in channels:
        reserve = c["channel_total_sat"] / 100
        sendable_amount = max(0, c["channel_sat"] - reserve)
        total_sendable_amount += sendable_amount
    assert(amount <= total_sendable_amount), "can only send %r but %r given" % (
        total_sendable_amount, amount)

    kappa, tau = helper_computer_node_parameters(channels)
    nu_target = float(tau - amount)/kappa
    channels = helper_compute_channel_balance_coefficients(channels)

    # compute rebalance amounts for channels with channel balance coefficients higher than targeted node balance coefficient
    total_rebalance_fractions = 0
    rebalance_fractions = {}
    for c in channels:
        if c["zeta"] > nu_target:
            rebalance_fraction = c["channel_total_sat"] * \
                (nu_target - c["zeta"])
            rebalance_fractions[c["short_channel_id"]] = rebalance_fraction
            total_rebalance_fractions += rebalance_fraction

    # round everything up. we are going to pay fees anyway. we could do msats but obfuscating is also nice
    return {k: int(v * amount / total_rebalance_fractions + 0.5)for k, v in rebalance_fractions.items()}, nu_target
