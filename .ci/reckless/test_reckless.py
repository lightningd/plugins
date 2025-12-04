import logging
import os
import pytest
import time
import subprocess
from pathlib import Path

from pyln.testing.fixtures import *  # noqa: F403

LOGGER = logging.getLogger(__name__)


def test_plugin_install_raw(node_factory, plugin_name):
    LOGGER.info(f"Testing reckless raw with: {plugin_name}")

    l1 = node_factory.get_node()

    ln_dir = str(Path(l1.info["lightning-dir"]).parent)

    subprocess.run(
        [
            "reckless",
            "-v",
            "--json",
            "-l",
            ln_dir,
            "--network",
            "regtest",
            "source",
            "remove",
            "https://github.com/lightningd/plugins",
        ],
        input="Y\n",
        text=True,
        capture_output=True,
    )

    subprocess.check_call(
        [
            "reckless",
            "-v",
            "--json",
            "-l",
            ln_dir,
            "--network",
            "regtest",
            "source",
            "add",
            f"{os.environ['GITHUB_WORKSPACE']}",
        ]
    )

    subprocess.check_call(
        [
            "reckless",
            "-v",
            "--json",
            "-l",
            ln_dir,
            "--network",
            "regtest",
            "install",
            plugin_name,
        ]
    )

    plugin_list = l1.rpc.call("plugin", ["list"])

    for plugin in plugin_list["plugins"]:
        if plugin_name in plugin["name"]:
            return
    pytest.fail(f"Plugin {plugin_name} not installed")


# def test_plugin_install(node_factory, plugin_name):
#     LOGGER.info(f"Testing reckless with: {plugin_name}")

#     l1 = node_factory.get_node()

#     l1.rpc.call(
#         "reckless", ["source", "remove", "https://github.com/lightningd/plugins"]
#     )

#     l1.rpc.call("reckless", ["source", "add", f"{os.environ['GITHUB_WORKSPACE']}"])

#     l1.rpc.call("reckless", ["install", plugin_name])

#     plugin_list = l1.rpc.call("plugin", ["list"])

#     for plugin in plugin_list["plugins"]:
#         if plugin_name in plugin["name"]:
#             return
#     pytest.fail(f"Plugin {plugin_name} not installed")
