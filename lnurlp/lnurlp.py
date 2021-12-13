#!/usr/bin/env python3

from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pyln.client import Plugin
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.wsgi import WSGIContainer
from werkzeug.middleware.proxy_fix import ProxyFix


import asyncio
import hashlib
import json
import os
import threading
import uuid

metadata = ""
plugin = Plugin()
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

jobs = {}


@app.route('/payRequest')
def payRequestUrl():
    global plugin
    amount = int(request.args.get('amount'))
    label = "ln-lnurlp-{}".format(uuid.uuid4())

    invoice = plugin.rpc.invoice(amount, label, "", description_hash=plugin.description_hash)

    return {'pr': invoice['bolt11'], 'routes': []}


def worker(address, port):
    asyncio.set_event_loop(asyncio.new_event_loop())

    print('Starting server on port {port}'.format(
        port=port
    ))
    app.config['SECRET_KEY'] = os.getenv(
        "REQUEST_INVOICE_SECRET",
        default=uuid.uuid4())

    http_server = HTTPServer(WSGIContainer(app))
    http_server.listen(port, address)
    IOLoop.instance().start()


def start_server(address, port):
    if port in jobs:
        raise ValueError("server already running on port {port}".format(port=port))

    p = threading.Thread(
        target=worker, args=(address, port), daemon=True)

    jobs[port] = p
    p.start()


@plugin.init()
def init(options, configuration, plugin):
    plugin.address = options["lnurlp-addr"]
    plugin.port = int(options["lnurlp-port"])
    ratelimit = options.get("lnurlp-ratelimit", "2 per minute")

    if ratelimit != "disable":
        limiter = Limiter(
            app,
            key_func=get_remote_address
        )
        limiter.limit(ratelimit)(payRequestUrl)

    try:
        with open(options["lnurlp-meta-path"], 'r') as f:
            metadata = json.load(f)['metadata'].encode()
            plugin.description_hash = hashlib.sha256(metadata).hexdigest()
    except FileNotFoundError:
        if options["lnurlp-meta-path"] == "":
            raise Exception("Please add a path to the webserver's json with --lnurlp-meta-path=...")
        else:
            raise Exception("File not found!")

    start_server(plugin.address, plugin.port)


plugin.add_option(
    "lnurlp-addr",
    "127.0.0.1",
    "Manually set the address to be used for the lnurlp-plugin, default is 127.0.0.1"
)

plugin.add_option(
    "lnurlp-port",
    "8806",
    "Manually set the port to be used for the lnurlp-plugin, default is 8806"
)

plugin.add_option(
    "lnurlp-meta-path",
    "",
    "Path of the webserver's lnurlp-JSON-file"
)

plugin.add_option(
    "lnurlp-ratelimit",
    "2 per minute",
    "Set flask's rate limiter, default is '2 per minute', 'disable' to disable"
)

plugin.run()
