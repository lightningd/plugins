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
from random import random


# change this
secret= 'caba27ba-45c7-4495-aa53-fd6a5866fbd8'


plugin = Plugin()
app = Flask(__name__)
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)


@limiter.limit("20 per minute")
def getinvoice(amount, description):       
        global plugin
        label = "ln-getinvoice-{}".format(random())
        invoice = plugin.rpc.invoice(int(amount)*1000, label, description)
        return invoice


def worker(port):
    app.config['SECRET_KEY'] = secret    
    app.add_url_rule('/invoice/<int:amount>/<description>', 'getinvoice', getinvoice)
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
def invoiceserver(request, command="start", port=8089):
    """Starts a server for requestiong invoices. 
    
    A rate limited HTTP Server returns a invoice on the following GET request:
    /invoice/<amount>/<description>  
    where amount is in Satoshis.  
    The plugin takes one of the following commands: 
    {start/stop/restart} and {port} .By default the plugin
    starts the server on port 8089.
    """
    commands = {"start", "stop", "restart", "list"}

    # if command unknown make start our default command
    if command not in commands:
        command = "start"

    # if port not an integer make 8088 as default
    try:
        port = int(port)
    except:
        port = int(plugin.options['invoice-web-port']['value'])

    if command == "list":
        return "servers running on the following ports: {}".format(list(jobs.keys()))

    if command == "start":
        if port in jobs:
            return "Server already running on port {}. Maybe restart the server?".format(port)
        suc = start_server(port)
        if suc:
            return "started server successfully on port {}".format(port)
        else:
            return "Could not start server on port {}".format(port)

    if command == "stop":
        if stop_server(port):
            return "stopped server on port{}".format(port)
        else:
            return "could not stop the server"

    if command == "restart":
        stop_server(port)
        suc = start_server(port)
        if suc:
            return "started server successfully on port {}".format(port)
        else:
            return "Could not start server on port {}".format(port)

plugin.add_option(
    'invoiceserver-autostart',
    'true',
    'Should the invoice server start automatically'
)

plugin.add_option(
    'invoiceserver-web-port',
    '8809',
    'Which port should the invoice server listen to?'
)



@plugin.init()
def init(options, configuration, plugin):
    port = int(options['invoiceserver-web-port'])

    if options['invoiceserver-autostart'].lower() in ['true', '1']:
        start_server(port)


plugin.run()
