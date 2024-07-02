#!/usr/bin/env python3
# Copyright (c) 2019 lightningd
# Distributed under the BSD 3-Clause License, see the accompanying file LICENSE

###############################################################################
# ZeroMQ publishing plugin for lightningd
#
# Using Twisted and txZMQ frameworks, this plugin binds to ZeroMQ endpoints and
# publishes notification of all possible subscriptions that have been opted-in
# for via lightningd launch parameter.
#
# This plugin doesn't interpret any of the content of the data which comes out
# of lightningd, it merely passes the received JSON through as encoded UTF-8,
# with the 'tag' being set to the Notification Type name (also encoded as
# UTF-8). It follows that adding future possible subscriptions *should* be as
# easy as appending it to NOTIFICATION_TYPE_NAMES below.
#
# The user-selectable configuration takes inspiration from the bitcoind ZeroMQ
# integration. The endpoint must be explicitly given as an argument to enable
# it. Also, the high water mark argument for the binding is set as an
# additional launch option.
#
# Due to how the plugins must register via getmanifest, this will opt-in to all
# subscriptions and ignore the messages from ones not bound to ZMQ endpoints.
# Hence, there might be a minor performance impact from subscription messages
# that result in no publish action. This can be mitigated by dropping
# notifications that are not of interest to your ZeroMQ subscribers from
# NOTIFICATION_TYPE_NAMES below.
###############################################################################

import json
import functools

from twisted.internet import reactor
from txzmq import ZmqEndpoint, ZmqEndpointType
from txzmq import ZmqFactory
from txzmq import ZmqPubConnection

from pyln.client import Plugin

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
    """Wrapper for notification type string to generate the corresponding
    plugin option strings. By convention of lightningd, the cli options
    use dashes in place of rather than underscores or no spaces."""

    def __init__(self, notification_type_name):
        self.notification_type_name = notification_type_name

    def __str__(self):
        return self.notification_type_name

    def endpoint_option(self):
        return "zmq-pub-{}".format(str(self).replace("_", "-"))

    def hwm_option(self):
        return "zmq-pub-{}-hwm".format(str(self).replace("_", "-"))


NOTIFICATION_TYPES = [NotificationType(n) for n in NOTIFICATION_TYPE_NAMES]

###############################################################################


class Publisher:
    """Holds the connection state and accepts incoming notifications that
    come from the subscription. If there is an associated publishing
    endpoint connected, it will encode and pass the contents of the
    notification."""

    def __init__(self):
        self.factory = ZmqFactory()
        self.connection_map = {}

    def load_setup(self, setup):
        for e, s in setup.items():
            endpoint = ZmqEndpoint(ZmqEndpointType.bind, e)
            ZmqPubConnection.highWaterMark = s["high_water_mark"]
            connection = ZmqPubConnection(self.factory, endpoint)
            for n in s["notification_type_names"]:
                self.connection_map[n] = connection

    def publish_notification(self, notification_type_name, *args, **kwargs):
        if notification_type_name not in self.connection_map:
            return
        tag = notification_type_name.encode("utf8")
        message = json.dumps(kwargs).encode("utf8")
        connection = self.connection_map[notification_type_name]
        connection.publish(message, tag=tag)


publisher = Publisher()

###############################################################################

ZMQ_TRANSPORT_PREFIXES = ["tcp://", "ipc://", "inproc://", "pgm://", "epgm://"]


class Setup:
    """Does some light validation of the plugin option input and generates a
    dictionary to configure the Twisted and ZeroMQ setup"""

    def _at_least_one_binding(options):
        n_bindings = sum(
            1 for o, v in options.items() if not o.endswith("-hwm") and v != "null"
        )
        return n_bindings > 0

    def _iter_endpoints_not_ok(options):
        for nt in NOTIFICATION_TYPES:
            endpoint_opt = nt.endpoint_option()
            endpoint = options[endpoint_opt]
            if endpoint != "null":
                if (
                    len(
                        [
                            1
                            for prefix in ZMQ_TRANSPORT_PREFIXES
                            if endpoint.startswith(prefix)
                        ]
                    )
                    != 0
                ):
                    continue
                yield endpoint

    def check_option_warnings(options, plugin):
        if not Setup._at_least_one_binding(options):
            plugin.log(
                "No zmq publish sockets are bound as per launch args", level="warn"
            )
        for endpoint in Setup._iter_endpoints_not_ok(options):
            plugin.log(
                ("Endpoint option {} doesn't appear to be recognized").format(endpoint),
                level="warn",
            )

    ###########################################################################

    def _iter_endpoint_setup(options):
        for nt in NOTIFICATION_TYPES:
            endpoint_opt = nt.endpoint_option()
            if options[endpoint_opt] == "null":
                continue
            endpoint = options[endpoint_opt]
            hwm_opt = nt.hwm_option()
            hwm = int(options[hwm_opt])
            yield endpoint, nt, hwm

    def get_setup_dict(options):
        setup = {}
        for e, nt, hwm in Setup._iter_endpoint_setup(options):
            if e not in setup:
                setup[e] = {"notification_type_names": [], "high_water_mark": hwm}
            setup[e]["notification_type_names"].append(str(nt))
            # use the lowest high water mark given for the endpoint
            setup[e]["high_water_mark"] = min(setup[e]["high_water_mark"], hwm)
        return setup

    ###########################################################################

    def log_setup_dict(setup, plugin):
        for e, s in setup.items():
            m = (
                "Endpoint {} will get events from {} subscriptions "
                "published with high water mark {}"
            )
            m = m.format(e, s["notification_type_names"], s["high_water_mark"])
            plugin.log(m)


###############################################################################

plugin = Plugin()


@plugin.init()
def init(options, configuration, plugin, **kwargs):
    Setup.check_option_warnings(options, plugin)
    setup_dict = Setup.get_setup_dict(options)
    Setup.log_setup_dict(setup_dict, plugin)
    reactor.callFromThread(publisher.load_setup, setup_dict)


def on_notification(notification_type_name, plugin, *args, **kwargs):
    if len(args) != 0:
        plugin.log("got unexpected args: {}".format(args), level="warn")
    reactor.callFromThread(
        publisher.publish_notification, notification_type_name, *args, **kwargs
    )


DEFAULT_HIGH_WATER_MARK = 1000

for nt in NOTIFICATION_TYPES:
    # subscribe to all notifications
    on = functools.partial(on_notification, str(nt))
    on.__annotations__ = {}  # needed to please Plugin._coerce_arguments()
    plugin.add_subscription(str(nt), on)
    # zmq socket binding option
    endpoint_opt = nt.endpoint_option()
    endpoint_desc = "Enable publish {} info to ZMQ socket endpoint".format(nt)
    plugin.add_option(endpoint_opt, None, endpoint_desc, opt_type="string")
    # high water mark option
    hwm_opt = nt.hwm_option()
    hwm_desc = "Set publish {} info message high water mark " "(default: {})".format(
        nt, DEFAULT_HIGH_WATER_MARK
    )
    plugin.add_option(hwm_opt, DEFAULT_HIGH_WATER_MARK, hwm_desc, opt_type="int")

###############################################################################


def plugin_thread():
    plugin.run()
    reactor.callFromThread(reactor.stop)


reactor.callInThread(plugin_thread)
reactor.run()
