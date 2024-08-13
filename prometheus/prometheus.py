#!/usr/bin/env python3
from pyln.client import Plugin
from prometheus_client import start_http_server, CollectorRegistry
from prometheus_client.core import InfoMetricFamily, GaugeMetricFamily
from sys import exit

plugin = Plugin()


class BaseLnCollector(object):
    def __init__(self, rpc, registry):
        self.rpc = rpc
        self.registry = registry


class NodeCollector(BaseLnCollector):
    def collect(self):
        info = self.rpc.getinfo()
        info_labels = {k.replace('-', '_'): v for k, v in info.items() if isinstance(v, str)}
        node_info_fam = InfoMetricFamily(
            'lightning_node',
            'Static node information',
            labels=info_labels.keys(),
        )
        node_info_fam.add_metric(info_labels, info_labels)
        yield node_info_fam

        blockheight = info['blockheight']
        yield GaugeMetricFamily(
            'lightning_node_blockheight',
            "Current Bitcoin blockheight on this node.",
            value=blockheight,
        )

        fees_msat = int(info.get(
            "fees_collected_msat",
            info.get("msatoshi_fees_collected", None)
        ))
        yield GaugeMetricFamily(
            'lightning_fees_collected_msat',
            'How much have we been paid to route payments?',
            value=fees_msat,
        )


class FundsCollector(BaseLnCollector):
    def collect(self):
        funds = self.rpc.listfunds()
        print(funds['outputs'])
        output_funds = sum(
            [o['amount_msat'] // 1000 for o in funds['outputs']]
        )
        channel_funds = sum(
            [c['our_amount_msat'] // 1000 for c in funds['channels']]
        )
        total = output_funds + channel_funds

        yield GaugeMetricFamily(
            'lightning_funds_total',
            "Total satoshis we own on this node.",
            value=total,
        )
        yield GaugeMetricFamily(
            'lightning_funds_output',
            "On-chain satoshis at our disposal",
            value=output_funds,
        )
        yield GaugeMetricFamily(
            'lightning_funds_channel',
            "Satoshis in channels.",
            value=channel_funds,
        )


class PeerCollector(BaseLnCollector):
    def collect(self):
        peers = self.rpc.listpeers()['peers']

        connected = GaugeMetricFamily(
            'lightning_peer_connected',
            'Is the peer currently connected?',
            labels=['id'],
        )
        count = GaugeMetricFamily(
            'lightning_peer_channels',
            "The number of channels with the peer",
            labels=['id'],
        )

        channels = self.rpc.listpeerchannels()['channels']
        # Associate each channel with a peer
        peers = {}
        conn = {}
        for c in channels:
            peer_id = c['peer_id']
            peers[peer_id] = peers.get(peer_id, 0) + 1
            conn[peer_id] = conn.get(peer_id, 0) + c['peer_connected']

        for p in peers.keys():
            labels = [p]
            count.add_metric(labels, peers[p])
            connected.add_metric(labels, conn.get(p, 0))

        return [count, connected]


class ChannelsCollector(BaseLnCollector):
    def collect(self):
        balance_gauge = GaugeMetricFamily(
            'lightning_channel_balance',
            'How many funds are at our disposal?',
            labels=['id', 'scid', 'alias'],
        )
        spendable_gauge = GaugeMetricFamily(
            'lightning_channel_spendable',
            'How much can we currently send over this channel?',
            labels=['id', 'scid', 'alias'],
        )
        total_gauge = GaugeMetricFamily(
            'lightning_channel_capacity',
            'How many funds are in this channel in total?',
            labels=['id', 'scid', 'alias'],
        )
        htlc_gauge = GaugeMetricFamily(
            'lightning_channel_htlcs',
            'How many HTLCs are currently active on this channel?',
            labels=['id', 'scid', 'alias'],
        )

        # Incoming routing statistics
        in_payments_offered_gauge = GaugeMetricFamily(
            'lightning_channel_in_payments_offered',
            'How many incoming payments did we try to forward?',
            labels=['id', 'scid', 'alias'],
        )
        in_payments_fulfilled_gauge = GaugeMetricFamily(
            'lightning_channel_in_payments_fulfilled',
            'How many incoming payments did we succeed to forward?',
            labels=['id', 'scid', 'alias'],
        )
        in_msatoshi_offered_gauge = GaugeMetricFamily(
            'lightning_channel_in_msatoshi_offered',
            'How many incoming msats did we try to forward?',
            labels=['id', 'scid', 'alias'],
        )
        in_msatoshi_fulfilled_gauge = GaugeMetricFamily(
            'lightning_channel_in_msatoshi_fulfilled',
            'How many incoming msats did we succeed to forward?',
            labels=['id', 'scid', 'alias'],
        )

        # Outgoing routing statistics
        out_payments_offered_gauge = GaugeMetricFamily(
            'lightning_channel_out_payments_offered',
            'How many outgoing payments did we try to forward?',
            labels=['id', 'scid', 'alias'],
        )
        out_payments_fulfilled_gauge = GaugeMetricFamily(
            'lightning_channel_out_payments_fulfilled',
            'How many outgoing payments did we succeed to forward?',
            labels=['id', 'scid', 'alias'],
        )
        out_msatoshi_offered_gauge = GaugeMetricFamily(
            'lightning_channel_out_msatoshi_offered',
            'How many outgoing msats did we try to forward?',
            labels=['id', 'scid', 'alias'],
        )
        out_msatoshi_fulfilled_gauge = GaugeMetricFamily(
            'lightning_channel_out_msatoshi_fulfilled',
            'How many outgoing msats did we succeed to forward?',
            labels=['id', 'scid', 'alias'],
        )

        channels = self.rpc.listpeerchannels()['channels']
        for c in channels:
            # append alias for human readable labels, if no label is found fill with shortid.
            node = self.rpc.listnodes(c['peer_id'])['nodes']
            if len(node) != 0 and 'alias' in node[0]:
                alias = node[0]['alias']
            else:
                alias = 'unknown'

            labels = [c['peer_id'], c.get('short_channel_id', c.get('channel_id')), alias]
            balance_gauge.add_metric(labels, c['to_us_msat'] // 1000)
            spendable_gauge.add_metric(labels,
                                       c['spendable_msat'] // 1000)
            total_gauge.add_metric(labels, c['total_msat'] // 1000)
            htlc_gauge.add_metric(labels, len(c['htlcs']))

            in_payments_offered_gauge.add_metric(labels, c['in_payments_offered'])
            in_payments_fulfilled_gauge.add_metric(labels, c['in_payments_fulfilled'])
            in_msatoshi_offered_gauge.add_metric(labels, int(c['in_offered_msat']))
            in_msatoshi_fulfilled_gauge.add_metric(labels, int(c['in_fulfilled_msat']))

            out_payments_offered_gauge.add_metric(labels, c['out_payments_offered'])
            out_payments_fulfilled_gauge.add_metric(labels, c['out_payments_fulfilled'])
            out_msatoshi_offered_gauge.add_metric(labels, int(c['out_offered_msat']))
            out_msatoshi_fulfilled_gauge.add_metric(labels, int(c['out_fulfilled_msat']))

        return [
            htlc_gauge,
            total_gauge,
            spendable_gauge,
            balance_gauge,
            in_payments_offered_gauge,
            in_payments_fulfilled_gauge,
            in_msatoshi_offered_gauge,
            in_msatoshi_fulfilled_gauge,
            out_payments_offered_gauge,
            out_payments_fulfilled_gauge,
            out_msatoshi_offered_gauge,
            out_msatoshi_fulfilled_gauge,
        ]


@plugin.init()
def init(options, configuration, plugin):
    s = options['prometheus-listen'].rpartition(':')
    if len(s) != 3 or s[1] != ':':
        print("Could not parse prometheus-listen address")
        exit(1)
    ip, port = s[0], int(s[2])

    registry = CollectorRegistry()
    start_http_server(addr=ip, port=port, registry=registry)
    registry.register(NodeCollector(plugin.rpc, registry))
    registry.register(FundsCollector(plugin.rpc, registry))
    registry.register(PeerCollector(plugin.rpc, registry))
    registry.register(ChannelsCollector(plugin.rpc, registry))


plugin.add_option(
    'prometheus-listen',
    '127.0.0.1:9750',
    'Address and port to bind to'
)


plugin.run()
