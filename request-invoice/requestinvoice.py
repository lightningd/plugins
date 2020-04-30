#!/usr/bin/env python3

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pathlib import Path
from pyln.client import Plugin
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.wsgi import WSGIContainer


import asyncio
import os
import threading
import uuid

# read or create file .lightning/bitcoin/.env
env_path = Path('.') / '.env'
if not env_path.exists():
    env_path.open('a')
    env_path.write_text("FLASKSECRET="+uuid.uuid4().hex +"\nFLASKPORT=8809"+"\nAUTOSTART=0")

plugin = Plugin()
app = Flask(__name__)
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["2000 per day", "20 per minute"]
)


jobs = {}



@limiter.limit("20 per minute")
@app.route('/invoice/<int:amount>/<description>')
def getinvoice(amount, description):
    global plugin
    label = "ln-getinvoice-{}".format(uuid.uuid4())
    invoice = plugin.rpc.invoice(int(amount)*1000, label, description)
    return invoice

def worker(port):
    asyncio.set_event_loop(asyncio.new_event_loop())

    print('Starting server on port {port}'.format(
        port=port
    ))
    app.config['SECRET_KEY'] = os.getenv(
        "REQUEST_INVOICE_SECRET",
        default=uuid.uuid4())

    http_server = HTTPServer(WSGIContainer(app))
    http_server.listen(port)
    IOLoop.instance().start()


def start_server(port):
    if port in jobs:
        raise ValueError("server already running on port {port}".format(port=port))

    p = threading.Thread(
        target=worker, args=(port,), daemon=True)

    jobs[port] = p
    p.start()


def stop_server(port):
    if port in jobs:
        jobs[port].terminate()
        del jobs[port]
    else:
        raise ValueError("No server listening on port {port}".format(port=port))


@plugin.method('invoiceserver')
def invoiceserver(request, command="start"):
    """Starts a server for requestiong invoices.

    A rate limited HTTP Server returns a invoice on the following GET request:
    /invoice/<amount>/<description>
    where amount is in Satoshis.
    The plugin takes one of the following commands:
    {start/stop/status/restart}.
    """
    commands = {"start", "stop", "status","restart"}
    port = os.getenv("FLASKPORT", default = 8809)

    # if command unknown make start our default command
    if command not in commands:
        command = "start"

    if command == "start":
        try:
            start_server(port)
            return "Invoice server started successfully on port {}".format(port)
        except Exception as e:
            return "Error starting server on port {port}: {e}".format(
                port=port, e=e
            )

    if command == "stop":
        try:
            stop_server(port)
            return "Invoice server stopped on port {}".format(port)
        except Exception as e:
            return "Could not stop server on port {port}: {e}".format(
                port=port, e=e
            )

    if command == "status":
        if port in jobs:
            return "Invoice server active on port {}".format(port)
        else:
            return "Invoice server not active."

    if command == "restart":
        stop_server(port)
        start_server(port)
        return "Invoice server restarted"


@plugin.init()
def init(options, configuration, plugin):
    port = os.getenv("REQUEST_INVOICE_PORT", default = 8809)
    start_server(port)


plugin.run()
