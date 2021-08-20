#!/usr/bin/env python3

# Better safe than sorry :-)
SUBSCRIBE_NOTIF = True
try:
    import notify2
except ImportError:
    SUBSCRIBE_NOTIF = False
import os
import sys

from pyln.client import LightningRpc, Plugin, RpcError
from PyQt5.QtWidgets import QApplication, QWidget, QMessageBox

from mainWindow import MainWindow
from utils import timeout_bool

class HackedLightningRpc(LightningRpc):
    """Dark side Lightning Rpc

    PyQt5 (after v5.5) will call qFatal() (and then abort()) when an exception is
    thrown in a slot. This behavior cannot be changed (C++ API) nor it can `except`ed.
    It means that if you make a Rpc call which raises an error in a slot (for example,
    randomly, `decodepay` with an user-entered value) it will exit the application
    without even a traceback : PyQt5.5 we <3 u.

    To avoid this behevior I thought of making hand checks before making a Rpc call in
    a slot (i.e. doing this for each Rpc call since a GUI is event-driven), or override
    the `call` method which raises exceptions to quiet the RPC exception and open a dialog
    for the user to understand what's happening. I chose the second method.
    """
    def call(self, method, payload=None):
        """Original call method with Qt-style exception handling"""
        try:
            return super(HackedLightningRpc, self).call(method, payload)
        except RpcError as e:
            QMessageBox.warning(None, "RPC error", str(e))
            pass
        return False # Rpc call failed

plugin = Plugin()

@plugin.init()
def init(options, configuration, plugin):
    if SUBSCRIBE_NOTIF:
        notify2.init("lightning-qt")
    path = os.path.join(plugin.lightning_dir, plugin.rpc_filename)
    # See above the docstring for rationale
    plugin.rpc = HackedLightningRpc(path)


@plugin.method("gui")
def gui(plugin):
    """Launches the Qt GUI"""
    app = QApplication([])
    win = MainWindow(plugin)
    win.show()
    return "Succesfully stopped lightning-qt" if not app.exec_() else "An error occured"


if SUBSCRIBE_NOTIF:
    @plugin.subscribe("connect")
    def peer_connected(plugin, id, address):
        n = notify2.Notification("C-lightning",
                                 "Peer with id {} and ip {} just connected to you"
                                 .format(id, address))
        n.show()

    @plugin.subscribe("disconnect")
    def peer_disconnected(plugin, id):
        n = notify2.Notification("C-lightning",
                                 "Peer with id {} just disconnected from you"
                                 .format(id))
        n.show()

    @plugin.subscribe("invoice_payment")
    def invoice_payment(plugin, invoice_payment):
        n = notify2.Notification("C-lightning",
                                 "Invoice with label {} was just paid."
                                 "Amount: {}"
                                 "Preimage: {}"
                                 .format(invoice_payment["label"],
                                        invoice_payment["preimage"],
                                        invoice_payment["msat"]))
        n.show()

    @plugin.subscribe("channel_opened")
    def channel_opened(plugin, channel_opened):
        n = notify2.Notification("C-lightning",
                                 "A channel was opened to you by {}, with an amount"
                                 " of {} and the following funding transaction id:"
                                 " {}.".format(channel_opened["id"],
                                            channel_opened["amount"],
                                            channel_opened["funding_txid"]))
        n.show()


if sys.stdin.isatty():
    print("Standalone mode")
    if len(sys.argv) == 1:
        print("Using default 'lightning-rpc' socket path")
        plugin.rpc = HackedLightningRpc(os.path.join(os.path.expanduser("~"), ".lightning", "lightning-rpc"))
    elif len(sys.argv) == 2:
        path = sys.argv[1].split("=")[1]
        plugin.rpc = HackedLightningRpc(path)
    elif len(sys.argv) == 3:
        plugin.rpc = HackedLightningRpc(sys.argv[2])
    else:
        print("lightning-qt, bitcoin-qt for lightningd")
        print("usage :")
        # Actually we don't mind the argument's name
        print("    python3 guy.py --socket-path /path/to/lightning-rpc/socket")
    # Sometimes a forwarded UNIX domain socket might be usable only after some writing
    while timeout_bool(2, plugin.rpc.getinfo):
        print(".")
    print(gui(plugin))
else:
    plugin.run()
