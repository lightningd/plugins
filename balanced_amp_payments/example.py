#!/usr/bin/python3
"""
author: Rene Pickhardt (rene.m.pickhardt@ntnu.no)
Date: 14.1.2020
License: MIT

some example code to demonstrate the functionality of the balanced pay code
which is used in the balanced_amp_payments_plugin. 

You will need a file called listfunds.json which should contain the output
of your lightning node's listfunds command. you can get it by:

lightning-cli listfunds > listfunds.json

and then run the script from the same directory

python3 example.py

=== Support: 
If you like my work consider a donation at https://patreon.com/renepickhardt or https://tallyco.in/s/lnbook
"""

import balanced_amp_payments as bp
import json


def helper_fn_parse_jsn(show_schema=False):
    f = open("listfunds.json")
    jsn = ""
    for l in f:
        if len(l) < 2:
            continue
        jsn = jsn + l
    listfunds = json.loads(jsn)["channels"]
    if show_schema:
        for el in listfunds:
            for k, v in el.items():
                print(k, v)
            break
    return listfunds


def display_results(channels, res, receiving=False):
    untouched_channel_stats = ""
    print("targeting for a balance coefficient of: {:4.2f}".format(nu))
    for chan in channels:
        sid = chan["short_channel_id"]
        cap = chan["channel_total_sat"]
        balance = chan["channel_sat"]
        zeta_old = float(balance)/cap

        if sid in res:
            if receiving:
                zeta_new = float(balance + res[sid])/cap
            else:
                zeta_new = float(balance - res[sid])/cap
            print("{}\t{}\t{}\t{}\t{:5.3f}\t{:5.3f}".format(
                sid, chan["channel_total_sat"], chan["channel_sat"], res[sid], zeta_old, zeta_new))
        else:
            untouched_channel_stats += "{}\t{}\t{}\t0\t{:5.3f}\t{:5.3f}\n".format(
                sid, chan["channel_total_sat"], chan["channel_sat"], zeta_old, zeta_old)
    if len(untouched_channel_stats) > 10:
        print("---- untouched_channels ----")
        print(untouched_channel_stats)


channels = helper_fn_parse_jsn(False)
res, nu = bp.recommend_outgoing_channels(channels, 14000000)
display_results(channels, res, receiving=False)

res, nu = bp.recommend_incoming_channels(channels, 60000000)
display_results(channels, res, receiving=True)
