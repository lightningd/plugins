#!/usr/bin/env python3
from pyln.client import Plugin
import json
import os
import psutil
import subprocess
import sys
import threading
import time

try:
    # C-lightning v0.7.2
    plugin = Plugin(dynamic=False)
except:
    plugin = Plugin()


class ChildPlugin(object):

    def __init__(self, path, plugin):
        self.path = path
        self.plugin = plugin
        self.status = 'stopped'
        self.proc = None
        self.iolock = threading.Lock()
        self.decoder = json.JSONDecoder()
        self.manifest = None
        self.init = None
        self.reader = None

    def watch(self):
        last = os.path.getmtime(self.path)
        while True:
            time.sleep(1)
            now = os.path.getmtime(self.path)
            if last != now:
                print("Detected a change in the child plugin, restarting...")
                last = now
                try:
                    self.restart()
                except Exception as e:
                    self.plugin.log(
                        "Failed to start plugin, will wait for next change and try again:",
                        level='error'
                    )

    def handle_init(self, request):
        """Lightningd has sent us its first init message, clean and forward.
        """
        params = request.params.copy()

        # These may have been added by the plugin framework and we won't be
        # able to serialize them when forwarding, so delete them.
        for key in ['plugin', 'request']:
            if key in params:
                del params[key]

        self.init = {
            'jsonrpc': '2.0',
            'method': request.method,
            'params': params,
            'id': request.id,
        }
        print("Forwarding", self.init)

        # Now remove any options that we registered on behalf of the child
        # plugin. It'd not understand them if we forward them.
        opts = self.init['params']['options']
        self.init['params']['options'] = {k: v for k, v in opts.items() if not k.startswith('autoreload')}
        plugin.child.send(self.init)
        print("Sent init to child plugin")
        plugin.child.passthru()

    def _readobj(self, sock):
        buff=b''
        while True:
            try:
                b = sock.readline()
                buff += b

                if len(b) == 0:
                    return None
                if b'}\n' not in buff:
                    continue
                # Convert late to UTF-8 so glyphs split across recvs do not
                # impact us
                buff = buff.decode("UTF-8")
                objs, len_used = self.decoder.raw_decode(buff)
                buff = buff[len_used:].lstrip().encode("UTF-8")
                return objs
            except ValueError:
                # Probably didn't read enough
                buff = buff.lstrip().encode("UTF-8")

    def start(self):
        assert(self.status == 'stopped')
        try:
            self.proc = subprocess.Popen([self.path], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
            self.status = 'started'
            manifest = self.getmanifest()
            return True
        except Exception as e:
            self.plugin.log(e, level='warn')
            return False

    def stop(self):
        assert(self.status == 'started')
        self.proc.kill()
        self.proc.wait()
        reader = self.reader
        if reader:
            reader.join()
        self.status = 'stopped'

    def restart(self):
        print('Restarting child plugin')
        self.stop()
        self.start()
        plugin.child.send(self.init)
        print("Sent init to child plugin")
        plugin.child.passthru()

    def getmanifest(self):
        assert(self.status == 'started')
        self.send({'jsonrpc': '2.0', 'id': 0, 'method': 'getmanifest', 'params': []})

        while True:
            msg = self._readobj(self.proc.stdout)

            if msg is None:
                print("Child plugin does not seem to be sending valid JSON: {}".format(buff.strip()))
                self.stop()
                raise ValueError()

            if 'id' in msg and msg['id'] == 0:

                if self.manifest is not None and msg['result'] != self.manifest:
                    plugin.log(
                        "Plugin manifest changed between restarts: {new} != {old}\n\n"
                        "==> You need to restart c-lightning for these changes to be picked up! <==".format(
                            new=json.dumps(msg['result'], indent=True).replace("\"", "'"),
                            old=json.dumps(self.manifest, indent=True).replace("\"", "'")
                    ), level='warn')
                    raise ValueError()
                self.manifest = msg['result']
                break
            self.plugin._write_locked(msg)
        return self.manifest

    def passthru(self):
        # First read the init reply, and then we can switch to passthru
        while True:
            msg = self._readobj(self.proc.stdout)
            if 'id' in msg and msg['id'] == self.init['id']:
                break
            self.plugin._write_locked(msg)

        def read_loop():
            while True:
                line = self.proc.stdout.readline()
                if line == b'':
                    break
                self.plugin.stdout.buffer.write(line)
                self.plugin.stdout.flush()
            self.reader = None
            print("Child plugin exited")
        self.reader = threading.Thread(target=read_loop)
        self.reader.daemon = True
        self.reader.start()

    def send(self, msg):
        self.proc.stdin.write(json.dumps(msg).encode('UTF-8'))
        self.proc.stdin.write(b'\n\n')
        self.proc.stdin.flush()

    def proxy_method(self, request, *args, **kwargs):
        raw = {
            'jsonrpc': '2.0',
            'method': request.method,
            'params': request.params,
            'id': request.id,
        }
        self.send(raw)

    def proxy_subscription(self, request, *args, **kwargs):
        raw = {
            'jsonrpc': '2.0',
            'method': request.method,
            'params': request.params,
        }
        self.send(raw)


@plugin.init()
def init(options, configuration, plugin, request):
    #import remote_pdb; remote_pdb.set_trace()
    if options['autoreload-plugin'] in ['null', None]:
        print("Cannot run the autoreload plugin on its own, please specify --autoreload-plugin")
        plugin.rpc.stop()
        return

    watch_thread = threading.Thread(target=plugin.child.watch)
    watch_thread.daemon = True
    watch_thread.start()
    plugin.child.handle_init(request)


def inject_manifest(plugin, manifest):
    """Once we have the manifest from the child plugin, inject it into our own.
    """
    for opt in manifest.get("options", []):
        plugin.add_option(opt['name'], opt['default'], opt['description'])

    for m in manifest.get("rpcmethods", []):
        plugin.add_method(m['name'], plugin.child.proxy_method, background=True)

    for s in manifest.get("subscriptions", []):
        plugin.add_subscription(s, plugin.child.proxy_subscription)

    for h in manifest.get("hooks", []):
        plugin.add_hook(h, plugin.child.proxy_method, background=True)


@plugin.method('autoreload-restart')
def restart(plugin):
    """Manually triggers a restart of the plugin controlled by autoreload.
    """
    child = plugin.child
    child.restart()


# We can't rely on @plugin.init to tell us the plugin we need to watch and
# reload since we need to start it to pass through its manifest before we get
# any cli options. So we're doomed to get our parent cmdline and parse out the
# argument by hand.
parent = psutil.Process().parent()
while parent.name() != 'lightningd':
    parent = parent.parent()
cmdline = parent.cmdline()
plugin.path = None

prefix = '--autoreload-plugin='

for c in cmdline:
    if c.startswith(prefix):
        plugin.path = c[len(prefix):]
        break

if plugin.path:
    plugin.child = ChildPlugin(plugin.path, plugin)

    # If we can't start on the first attempt we can't inject into the
    # manifest, no point in continuing.
    if not plugin.child.start():
        raise Exception("Could not start the plugin under development, can't continue")

    inject_manifest(plugin, plugin.child.manifest)

else:
    plugin.log("Could not locate the plugin to control: {cmdline}".format(cmdline=cmdline))
    sys.exit(1)


# Now we can run the actual plugin
plugin.add_option("autoreload-plugin", None, "Path to the plugin that we should be watching and reloading.")
plugin.run()
