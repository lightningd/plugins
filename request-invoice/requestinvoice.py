#!/usr/bin/env python3

import multiprocessing
from flask import Flask
from flask import jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop

from pyln.client import LightningRpc, Plugin
from time import time
import os, uuid

from dotenv import load_dotenv, find_dotenv
from pathlib import Path

# read or create file .lightning/bitcoin/.env
env_path = Path('.') / '.env'
if not env_path.exists():
    env_path.open('a')
    env_path.write_text("FLASKSECRET="+uuid.uuid4().hex +"\nFLASKPORT=8809"+"\nAUTOSTART=0")
load_dotenv(str(env_path))

plugin = Plugin()
app = Flask(__name__)
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["2000 per day", "20 per minute"]
)

@limiter.limit("20 per minute")
@app.route('/invoice/<int:amount>/<description>')
def getinvoice(amount, description):
    global plugin
    label = "ln-getinvoice-{}".format(uuid.uuid4())
    invoice = plugin.rpc.invoice(int(amount)*1000, label, description)
    return invoice

def worker(port):
    print('starting server')
    app.config['SECRET_KEY'] = os.getenv("FLASKSECRET", default = uuid.uuid4())
    http_server = HTTPServer(WSGIContainer(app))
    http_server.listen(port)
    IOLoop.instance().start()
    return

jobs = {}

def start_server(port):
    if port in jobs:
        return False, "server already running"

    p = multiprocessing.Process(
        target=worker, args=[port], name="server on port {}".format(port))
    p.daemon = True

    jobs[port] = p
    p.start()
    return True

def stop_server(port):
    if port in jobs:
        jobs[port].terminate()
        del jobs[port]
        return True
    else:
        return False


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
        if port in jobs:
            return "Invoice server already running on port {}.".format(port)
        if start_server(port):
            return "Invoice server started successfully on port {}".format(port)
        else:
            return "Invoice server could not be started on port {}".format(port)

    if command == "stop":
        if stop_server(port):
            return "Invoice server stopped on port {}".format(port)
        else:
            if port in jobs:
                return "Could not stop the Invoice server."
            else:
                return "Invoice server doen't seem to be active"

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
    port = os.getenv("FLASKPORT", default = 8809)

    if os.getenv("AUTOSTART") == 1:
        start_server(port)

plugin.run()
