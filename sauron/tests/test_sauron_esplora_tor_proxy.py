#!/usr/bin/python

import os

import pyln
import pytest
from pyln.testing import utils
from pyln.testing.fixtures import *  # noqa: F403
from util import LightningD

pyln.testing.fixtures.network_daemons["bitcoin"] = utils.BitcoinD


class LightningNode(utils.LightningNode):
    def __init__(self, *args, **kwargs):
        pyln.testing.utils.TEST_NETWORK = "bitcoin"
        utils.LightningNode.__init__(self, *args, **kwargs)
        lightning_dir = args[1]

        self.daemon = LightningD(lightning_dir, None)  # noqa: F405
        options = {
            "disable-plugin": "bcli",
            "network": "bitcoin",
            "plugin": os.path.join(os.path.dirname(__file__), "../sauron.py"),
            "sauron-api-endpoint": "https://blockstream.info/api",
            "sauron-tor-proxy": "localhost:9050",
        }
        self.daemon.opts.update(options)

    # Monkey patch
    def set_feerates(self, feerates, wait_for_effect=True):
        return None


@pytest.fixture
def node_cls(monkeypatch):
    monkeypatch.setenv("TEST_NETWORK", "bitcoin")
    yield LightningNode


@pytest.mark.skip(reason="TODO: Add mock for tor proxy")
def test_tor_proxy(node_factory):
    """
    Test for tor proxy
    """
    ln_node = node_factory.get_node()

    assert ln_node.daemon.opts["sauron-tor-proxy"] == "localhost:9050"
    assert ln_node.daemon.is_in_log("Using proxy socks5h://localhost:9050 for requests")
