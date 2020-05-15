from pyln.testing.fixtures import *
import shutil
import subprocess
import time
import os
import unittest

def copy_plugin(src, directory, filename=None):
    base = os.path.dirname(__file__)
    src = os.path.join(base, src)
    dst = os.path.join(directory, filename if filename is not None else os.path.basename(src))
    shutil.copy(src, dst)
    shutil.copystat(src, dst)
    return dst


def test_restart_on_change(node_factory, directory):

    # Copy the dummy plugin over
    plugin = copy_plugin("dummy.py", directory, "plugin.py")

    opts = {
        'plugin': os.path.join(os.path.dirname(__file__), "..", 'autoreload.py'),
        'autoreload-plugin': plugin,
    }

    l1 = node_factory.get_node(options=opts)

    subprocess.check_call(['touch', plugin])
    l1.daemon.wait_for_log(r'Detected a change in the child plugin, restarting')


@unittest.skipIf(True, "Doesn't work on travis yet")
def test_changing_manifest(node_factory, directory):
    """Change the manifest in-between restarts.

    Adding an RPC method like the switch from dummy.py to dummy2.py does,
    should result in an error while reloading the plugin.

    """

    # Copy the dummy plugin over
    plugin = copy_plugin("dummy.py", directory, "plugin.py")
    plugin_path = os.path.join(os.path.dirname(__file__), "..", 'autoreload.py')
    opts = {
        'plugin': os.path.join(os.path.dirname(__file__), "..", 'autoreload.py'),
        'autoreload-plugin': plugin,
    }

    l1 = node_factory.get_node(options=opts, allow_broken_log=True)


    plugin = copy_plugin("dummy2.py", directory, "plugin.py")
    time.sleep(10)
    subprocess.check_call(['touch', plugin_path])
    time.sleep(10)
    subprocess.check_call(['touch', plugin_path])
    l1.daemon.wait_for_log(r'Detected a change in the child plugin, restarting')
    l1.daemon.wait_for_log(r'You need to restart c-lightning')
