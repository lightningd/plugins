#!/usr/bin/env python3
from collections import OrderedDict
from pyln.client import Plugin, Millisatoshi

from descriptions import goodpeers_small_desc, goodpeers_desc

plugin = Plugin()


def get_channel_infos(chan):
    """
    Filter out what we need from a channel entry in listchannels
    """
    return {
        "scid": chan["short_channel_id"],
        "ppm_fee": chan["fee_per_millionth"],
        "base_fee": chan["base_fee_millisatoshi"],
        "value": chan["amount_msat"],
    }


def get_nodes(plugin):
    """
    Get public Lightning network nodes.

    :return: A dict with the node id as key, and a list of channels as values.
    """
    peers = {}
    channels = plugin.rpc.listchannels()
    for chan in channels["channels"]:
        if chan["fee_per_millionth"] == chan["base_fee_millisatoshi"] == 0:
            # They are likely an agreement or the same person, they'd just
            # distort the medians.
            continue
        if not chan["active"]:
            # It could just be temporary, but we don't want zombies!
            continue
        id = chan["source"]
        if id not in peers.keys():
            peers[id] = []
        peers[id].append(get_channel_infos(chan))
    return peers


def filter_nodes(nodes):
    """
    Filter out nodes with <=15 non-dust channels.

    55$ minimum for a bitcoin at 8500$ (650000000 msats).
    """
    filtered_nodes = {}
    dust_limit = Millisatoshi(650000000)
    for id, channs in nodes.items():
        if len(list(filter(lambda c: c["value"] > dust_limit, channs))) > 15:
            filtered_nodes[id] = channs
    return filtered_nodes


def get_medians(channels):
    """
    Return the (median_base_fee, median_fees_ppm) of the given peer.
    """
    # Loop only once..
    base_fees = ppm_fees = []
    for chann in channels:
        base_fees.append(chann["base_fee"])
        ppm_fees.append(chann["ppm_fee"])
    base_fees, ppm_fees = sorted(base_fees), sorted(ppm_fees)
    n_channs = len(channels)
    if n_channs % 2 == 0:
        return base_fees[n_channs // 2], ppm_fees[n_channs // 2]
    else:
        median_base = (base_fees[n_channs // 2] +
                       base_fees[n_channs // 2 + 1]) / 2
        median_ppm = (ppm_fees[n_channs // 2] +
                      ppm_fees[n_channs // 2 + 1]) / 2
        return median_base, median_ppm


def reverse_sort(nodes):
    """
    Reversely sort the nodes, the lower the score the better.
    """
    # Python3.5 hasn't native dicts ordered.. So use OrderedDict
    return OrderedDict(sorted(nodes.items(),
                       key=lambda item: item[1]["score"], reverse=True))


@plugin.method("goodpeers", desc=goodpeers_small_desc,
               long_desc=goodpeers_desc)
def goodpeers(plugin, bias=None, **kwargs):
    nodes = get_nodes(plugin)
    # Leaf nodes and low-value channels nodes are not good peers..
    nodes = filter_nodes(nodes)
    # Add a score to each peer about its fees
    for id, channs in nodes.items():
        base, ppm = get_medians(channs)
        if not bias:
            score = float(base + ppm)
        elif bias.lower() == "small":
            score = float(base * 100 + ppm)
        elif bias.lower() == "big":
            score = float(base + ppm * 100)
        else:
            raise ValueError("Bad bias, should be 'big' or 'small'")
        nodes[id] = {
            "median_base": base,
            "median_ppm": ppm,
            "score": score,
        }
    # If used in the cli, better to reverse it !
    return reverse_sort(nodes)


plugin.run()
