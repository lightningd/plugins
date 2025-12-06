#!/usr/bin/env python3
# Copyright (c) 2019 lightningd
# Distributed under the BSD 3-Clause License, see the accompanying file LICENSE

###############################################################################
# An example ZeroMQ subscriber client for the plugin.
#
# This module connects and subscribes to ZeroMQ endpoints, decodes the messages
# and simply logs the JSON payload to stdout.
#
# It also uses Twisted and txZMQ frameworks, but on the subscriber side.
#
# To use, the plugin must be loaded for lightningd and the parameters must be
# given as launch arguments to publish notifications at given endpoints.
# Eg. for publishing 'connect' and 'disconnect' notifications:.
# $ lightningd --zmq-pub-connect=ipc:///tmp/cl-zmq  \
#              --zmq-pub-disconnect=tcp://127.0.0.1:5555
#
# The client must then be started with arguments for the same endpoints.
# Eg. to subscribe to those 'connect' and 'disconnect' notifications:
#
# $ python3 example-subscriber.py --zmq-sub-connect=ipc:///tmp/cl-zmq \
#                                 --zmq-sub-disconnect=tcp://127.0.0.1:5555
#
# You can test receiving the subscription by connecting and disconnecting from
# nodes on the network:
# Eg.
# $ lightning-cli connect <node-id>
# $ lightning-cli disconnect <node-id>
#
###############################################################################

import time
import json
import argparse

from twisted.internet import reactor

from txzmq import ZmqEndpoint, ZmqEndpointType
from txzmq import ZmqFactory
from txzmq import ZmqSubConnection

###############################################################################

NOTIFICATION_TYPE_NAMES = [
    "channel_opened",
    "connect",
    "disconnect",
    "invoice_payment",
    "warning",
    "forward_event",
    "sendpay_success",
    "sendpay_failure",
]


class NotificationType:
    def __init__(self, notification_type_name):
        self.notification_type_name = notification_type_name

    def __str__(self):
        return self.notification_type_name

    def endpoint_option(self):
        return "zmq-sub-{}".format(str(self).replace("_", "-"))

    def argparse_namespace_attribute(self):
        return "zmq_sub_{}".format((self))


NOTIFICATION_TYPES = [NotificationType(n) for n in NOTIFICATION_TYPE_NAMES]

###############################################################################


class Subscriber:
    def __init__(self):
        self.factory = ZmqFactory()

    def _log_message(self, message, tag):
        tag = tag.decode("utf8")
        message = json.dumps(
            json.loads(message.decode("utf8")), indent=1, sort_keys=True
        )
        current_time = time.strftime("%X %x %Z")
        print("{} - {}\n{}".format(current_time, tag, message))

    def _load_setup(self, setup):
        for e, notification_type_names in setup.items():
            endpoint = ZmqEndpoint(ZmqEndpointType.connect, e)
            connection = ZmqSubConnection(self.factory, endpoint)
            for n in notification_type_names:
                tag = n.encode("utf8")
                connection.gotMessage = self._log_message
                connection.subscribe(tag)

    def parse_and_load_settings(self, settings):
        setup = {}
        for nt in NOTIFICATION_TYPES:
            attr = nt.argparse_namespace_attribute()
            endpoint = getattr(settings, attr)
            if endpoint is None:
                continue
            if endpoint not in setup:
                setup[endpoint] = []
            setup[endpoint].append(str(nt))
        self._load_setup(setup)


###############################################################################

parser = argparse.ArgumentParser(prog="example-subscriber.py")
for nt in NOTIFICATION_TYPES:
    h = "subscribe to {} events published from this endpoint".format(nt)
    parser.add_argument("--" + nt.endpoint_option(), type=str, help=h)
settings = parser.parse_args()

subscriber = Subscriber()
subscriber.parse_and_load_settings(settings)
reactor.run()
