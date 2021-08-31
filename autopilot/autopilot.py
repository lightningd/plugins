#!/usr/bin/env python3

from bech32 import bech32_decode, convertbits
from lib_autopilot import Autopilot, Strategy
from pyln.client import Plugin, RpcError
import random
import threading
import math
import networkx as nx
import dns.resolver
import time


plugin = Plugin()


class CLightning_autopilot(Autopilot):

    def __init__(self, rpc):
        self.__rpc_interface = rpc

        print("No input specified download graph from peers")
        G = self.__download_graph()
        Autopilot.__init__(self, G)

    def __get_seed_keys(self):
        """
        retrieve the nodeids of the ln seed nodes from lseed.bitcoinstats.com
        """
        domain = "lseed.bitcoinstats.com"
        srv_records = dns.resolver.query(domain, "SRV")
        res = []
        for srv in srv_records:
            bech32 = str(srv.target).rstrip(".").split(".")[0]
            data = bech32_decode(bech32)[1]
            decoded = convertbits(data, 5, 4)
            res.append("".join(
                ['{:1x}'.format(integer) for integer in decoded])[:-1])
        return res

    def __connect_to_seeds(self):
        """
        sets up peering connection to seed nodes of the lightning network

        This is necessary in case the node operating the autopilot has never
        been connected to the lightning network.
        """
        seed_keys = self.__get_seed_keys()
        random.shuffle(seed_keys)
        for nodeid in seed_keys:
            try:
                print("peering with node: {}".format(nodeid))
                self.__rpc_interface.connect(nodeid)
                # FIXME: better strategy than sleep(2) for building up
                time.sleep(2)
            except RpcError as e:
                print("Unable to connect to node: {}".format(nodeid))
                print(e)

    def __download_graph(self):
        """
        Downloads a local copy of the nodes view of the lightning network

        This copy is retrieved by listnodes and listedges RPC calls and will
        thus be incomplete as peering might not be ready yet.
        """

        # FIXME: it is a real problem that we don't know how many nodes there
        # could be. In particular billion nodes networks will outgrow memory
        G = nx.Graph()
        print("Instantiated networkx graph to store the lightning network")

        nodes = []
        print("Attempt RPC-call to download nodes from the lightning network")
        try:
            while len(nodes) == 0:
                peers = self.__rpc_interface.listpeers()["peers"]
                if len(peers) < 1:
                    self.__connect_to_seeds()
                nodes = self.__rpc_interface.listnodes()["nodes"]
        except ValueError as e:
            print("Node list could not be retrieved from the peers of the lightning network")
            raise e

        for node in nodes:
            G.add_node(node["nodeid"], **node)

        print("Number of nodes found and added to the local networkx graph: {}".format(len(nodes)))

        channels = {}
        try:
            print("Attempt RPC-call to download channels from the lightning network")
            channels = self.__rpc_interface.listchannels()["channels"]
            print("Number of retrieved channels: {}".format(len(channels)))
        except ValueError:
            print("Channel list could not be retrieved from the peers of the lightning network")
            return False

        for channel in channels:
            G.add_edge(
                channel["source"],
                channel["destination"],
                **channel)

        return G

    def connect(self, candidates, balance=1000000, dryrun=False):
        pdf = self.calculate_statistics(candidates)
        connection_dict = self.calculate_proposed_channel_capacities(pdf, balance)
        messages = []
        for nodeid, fraction in connection_dict.items():
            try:
                satoshis = min(math.ceil(balance * fraction), 16777215)
                messages.append(f"Try to open channel with a capacity of {satoshis} to node {nodeid}")
                plugin.log(messages[-1])
                if not dryrun:
                    self.__rpc_interface.connect(nodeid)
                    self.__rpc_interface.fundchannel(nodeid, satoshis, None, True, 0)
            except ValueError as e:
                messages.append(f"Could not open a channel to {nodeid} with capacity of {satoshis}. Error: {str(e)}")
                plugin.log(messages[-1], 'error')
        return messages


@plugin.init()
def init(configuration, options, plugin):
    plugin.num_channels = int(options['autopilot-num-channels'])
    plugin.percent = int(options['autopilot-percent'])
    plugin.min_capacity_sat = int(options['autopilot-min-channel-size-msat']) / 1000
    plugin.initialized = threading.Event()
    plugin.autopilot = None
    plugin.initerror = None
    print('Initialized autopilot function')

    def initialize_autopilot():
        try:
            plugin.autopilot = CLightning_autopilot(plugin.rpc)
        except Exception as e:
            plugin.initerror = e
        plugin.initialized.set()

    # Load the autopilot in the background and have it notify
    # dependents once we're finished.
    threading.Thread(target=initialize_autopilot, daemon=True).start()


@plugin.method('autopilot-run-once')
def run_once(plugin, dryrun=False):
    """
    Run the autopilot manually one time.

    The argument 'dryrun' can be set to True in order to just output what would
    be done without actually opening any channels.
    """
    # Let's start by inspecting the current state of the node
    funds = plugin.rpc.listfunds()
    awaiting_lockin_funds = sum([o['channel_sat'] for o in funds['channels'] if o['state'] == 'CHANNELD_AWAITING_LOCKIN'])
    output_funds = sum([o['value'] for o in funds['outputs'] if o['status'] == 'confirmed']) - awaiting_lockin_funds
    channels = funds['channels']
    available_funds = output_funds / 100.0 * plugin.percent

    # Now we can look whether and how we'd like to open new channels. This
    # depends on available funds and the number of channels we were configured
    # to open

    if available_funds < plugin.min_capacity_sat:
        print("Too low available funds: {} < {}".format(available_funds, plugin.min_capacity_sat))
        return False

    if len(channels) >= plugin.num_channels:
        print("Already have {} channels. Aim is for {}.".format(len(channels), plugin.num_channels))
        return False

    num_channels = min(
        int(available_funds / plugin.min_capacity_sat),
        plugin.num_channels - len(channels)
    )

    # Each channel will have this capacity
    channel_capacity = math.floor(available_funds / num_channels)

    print("I'd like to open {} new channels with {} satoshis each".format(num_channels, channel_capacity))

    plugin.initialized.wait()
    if plugin.initerror:
        return f"Error: autopilot had initialization errors: {str(plugin.initerror)}"

    candidates = plugin.autopilot.find_candidates(
        num_channels,
        strategy=Strategy.DIVERSE,
        percentile=0.5
    )
    return plugin.autopilot.connect(candidates, available_funds, dryrun=dryrun)


plugin.add_option(
    'autopilot-percent',
    '75',
    'What percentage of funds should be under the autopilots control?'
)


plugin.add_option(
    'autopilot-num-channels',
    '10',
    'How many channels should the autopilot aim for?'
)


plugin.add_option(
    'autopilot-min-channel-size-msat',
    '100000000',
    'Minimum channel size to open.',
)


plugin.run()
