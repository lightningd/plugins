import logging
import os
import re

from pyln.client import Millisatoshi
from pyln.testing.fixtures import *  # noqa: F401,F403

plugin_dir = os.path.dirname(__file__)
plugin_path = os.path.join(plugin_dir, "currencyrate.py")

LOGGER = logging.getLogger(__name__)

deprecated_apis = False


def extract_digits(value):
    if isinstance(value, Millisatoshi):
        return int(value)
    else:
        pattern = r"^(\d+)msat$"
        regex = re.compile(pattern)
        match = regex.match(value)
        if match:
            digits = match.group(1)
            return int(digits)
        else:
            return None


def test_currencyrate(node_factory):
    opts = {
        "plugin": plugin_path,
        "allow-deprecated-apis": deprecated_apis,
        "disable-source": ["bitstamp", "coinbase"],
    }
    l1 = node_factory.get_node(options=opts)
    plugins = [os.path.basename(p["name"]) for p in l1.rpc.plugin("list")["plugins"]]
    assert "currencyrate.py" in plugins

    rates = l1.rpc.call("currencyrates", ["USD"])
    LOGGER.info(rates)
    assert "bitstamp" not in rates
    assert "coinbase" not in rates
    assert "coingecko" in rates
    assert extract_digits(rates["coingecko"]) > 0

    ln_moscow_time = l1.rpc.call("currencyconvert", [100, "USD"])
    LOGGER.info(ln_moscow_time)
    assert "msat" in ln_moscow_time
    assert extract_digits(ln_moscow_time["msat"]) > 0
