'''
Created on 04.09.2018

@author: rpickhardt

This software is a command line tool and c-lightning wrapper for lib_autopilot

You need to have a c-lightning node running in order to utilize this program.
Also you need lib_autopilot. You can run

python3 c-lightning-autopilot --help

in order to get all the command line options

usage: c-lightning-autopilot.py [-h] [-b BALANCE] [-c CHANNELS]
                                [-r PATH_TO_RPC_INTERFACE]
                                [-s {diverse,merge}] [-p PERCENTILE_CUTOFF]
                                [-d] [-i INPUT]

optional arguments:
  -h, --help            show this help message and exit
  -b BALANCE, --balance BALANCE
                        use specified number of satoshis to open all channels
  -c CHANNELS, --channels CHANNELS
                        opens specified amount of channels
  -r PATH_TO_RPC_INTERFACE, --path_to_rpc_interface PATH_TO_RPC_INTERFACE
                        specifies the path to the rpc_interface
  -s {diverse,merge}, --strategy {diverse,merge}
                        defines the strategy
  -p PERCENTILE_CUTOFF, --percentile_cutoff PERCENTILE_CUTOFF
                        only uses the top percentile of each probability
                        distribution
  -d, --dont_store      don't store the network on the hard drive
  -i INPUT, --input INPUT
                        points to a pickle file

a good example call of the program could look like that:

python3 c-lightning-autopilot.py -s diverse -c 30 -b 10000000

This call would use up to 10'000'000 satoshi to create 30 channels which are
generated by using the diverse strategy to mix the 4 heuristics.

Currently the software will not check, if sufficient funds are available
or if a channel already exists.
'''

from os.path import expanduser
import argparse
import logging
import math
import pickle
import sys

from pyln.client import LightningRpc
import dns.resolver

from bech32 import bech32_decode, CHARSET, convertbits
from lib_autopilot import Autopilot
from lib_autopilot import Strategy
import networkx as nx


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--balance",
                        help="use specified number of satoshis to open all channels")
    parser.add_argument("-c", "--channels",
                        help="opens specified amount of channels")
    # FIXME: add the following command line option
    # parser.add_argument("-m", "--maxchannels",
    #                help="opens channels as long as maxchannels is not reached")
    parser.add_argument("-r", "--path_to_rpc_interface",
                        help="specifies the path to the rpc_interface")
    parser.add_argument("-s", "--strategy", choices=[Strategy.DIVERSE, Strategy.MERGE],
                        help="defines the strategy ")
    parser.add_argument("-p", "--percentile_cutoff",
                        help="only uses the top percentile of each probability distribution")
    parser.add_argument("-d", "--dont_store", action='store_true',
                        help="don't store the network on the hard drive")
    parser.add_argument("-i", "--input",
                        help="points to a pickle file")

    args = parser.parse_args()

    # FIXME: find ln-dir from lightningd.
    path = path = expanduser("~/.lightning/lightning-rpc")
    if args.path_to_rpc_interface is not None:
        path = expanduser(parser.path-to-rpc-interface)

    balance = 1000000
    if args.balance is not None:
        # FIXME: parser.argument does not accept type = int
        balance = int(args.balance)

    num_channels = 21
    if args.channels is not None:
        # FIXME: parser.argument does not accept type = int
        num_channels = int(args.channels)

    percentile = None
    if args.percentile_cutoff is not None:
        # FIXME: parser.argument does not accept type = float
        percentile = float(args.percentile_cutoff)

    autopilot = CLightning_autopilot(path, input=args.input,
                                     dont_store=args.dont_store)

    candidates = autopilot.find_candidates(num_channels,
                                           strategy=args.strategy,
                                           percentile=percentile)

    autopilot.connect(candidates, balance)
    print("Autopilot finished. We hope it did a good job for you (and the lightning network). Thanks for using it.")
