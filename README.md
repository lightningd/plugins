# Plugins for c-lightning

Community curated plugins for c-lightning.

[![Build Status](https://travis-ci.org/lightningd/plugins.svg?branch=master)](https://travis-ci.org/lightningd/plugins)
[![Coverage Status](https://codecov.io/gh/lightningd/plugins/branch/master/graph/badge.svg)](https://codecov.io/gh/lightningd/plugins)

## Available plugins

| Name                               | Short description                                                          |
|------------------------------------|----------------------------------------------------------------------------|
| [autopilot][autopilot]             | An autopilot that suggests channels that should be established             |
| [autoreload][autoreload]           | A developer plugin that reloads a plugin under development when it changes |
| [csvexportpays][csvexportpays]     | A plugin that exports all payments to a CSV file                           |
| [donations][donations]             | A simple donations page to accept donations from the web                   |
| [drain][drain]                     | Draining, filling and balancing channels with automatic chunks.            |
| [graphql][graphql]                 | Exposes the c-lightning API over [graphql][graphql-spec]                   |
| [lightning-qt][lightning-qt]       | A bitcoin-qt-like GUI for lightningd                                       |
| [monitor][monitor]                 | helps you analyze the health of your peers and channels                    |
| [persistent-channels][pers-chans]  | Maintains a number of channels to peers                                    |
| [probe][probe]                     | Regularly probes the network for stability                                 |
| [prometheus][prometheus]           | Lightning node exporter for the prometheus timeseries server               |
| [rebalance][rebalance]             | Keeps your channels balanced                                               |
| [reckless][reckless]               | An **experimental** plugin manager (search/install plugins)                |
| [sauron][sauron]                   | A Bitcoin backend relying on [Esplora][esplora]'s API                      |
| [sendinvoiceless][sendinvoiceless] | Sends some money without an invoice from the receiving node.               |
| [sitzprobe][sitzprobe]             | A Lightning Network payment rehearsal utility                              |
| [summary][summary]                 | Print a nice summary of the node status                                    |
| [zmq][zmq]                         | Publishes notifications via [ZeroMQ][zmq-home] to configured endpoints     |


## Installation

To install and activate a plugin you need to stop your lightningd and restart it
with the `plugin` argument like this:

```
lightningd --plugin=/path/to/plugin/directory/plugin_file_name.py
```

Notes:
 - The `plugin_file_name.py` must have executable permissions:
   `chmod a+x plugin_file_name.py`
 - A plugin can be written in any programming language, as it interacts with
   `lightningd` purely using stdin/stdout pipes.

### Automatic plugin initialization

Alternatively, especially when you use multiple plugins, you can copy or symlink
all plugin directories into your `~/.lightning/plugins` directory. The daemon
will load each executeable it finds in sub-directories as a plugin. In this case
you don't need to manage all the `--plugin=...` parameters.

### PYTHONPATH and `pyln`

To simplify plugin development you can rely on `pyln-client` for the plugin
implementation, `pyln-proto` if you need to parse or write lightning protocol
messages, and `pyln-testing` in order to write tests. These libraries can be
retrieved in a number of different ways:

 - Using `pip` tools: `pip3 install pyln-client pyln-testing`
 - Using the `PYTHONPATH` environment variable to include your clightning's
   shipped `pyln-*` libraries:

```bash
export PYTHONPATH=/path/to/lightnind/contrib/pyln-client:/path/to/lightnind/contrib/pyln-testing:$PYTHONPATH
```

### Writing tests

The `pyln-testing` library provides a number of helpers and fixtures to write
tests. While not strictly necessary, writing a test will ensure that your
plugin is working correctly against a number of configurations (both with and
without `DEVELOPER`, `COMPAT` and `EXPERIMENTAL_FEATURES`), and more
importantly that they will continue to work with newly release versions of
c-lightning.

Writing a test is as simple as this:

- The framework will look for unittest filenames starting with `test_`.
- The test functions should also start with `test_`.

```python
from pyln.testing.fixtures import *

pluginopt = {'plugin': os.path.join(os.path.dirname(__file__), "YOUR_PLUGIN.py")}

def test_your_plugin(node_factory, bitcoind):
    l1 = node_factory.get_node(options=pluginopt)
    s = l1.rpc.summary()
    s = l1.rpc.getinfo()
    assert(s['network'] == 'REGTEST')  # or whatever you want to test
```

Tests are run against pull requests, all commits on `master`, as well as once
ever 24 hours to test against the latest `master` branch of the c-lightning
development tree.

Running tests locally can be done like this:
(make sure the `PYTHONPATH` env variable is correct)

```bash
pytest YOUR_PLUGIN/YOUR_TEST.py
```

### Additional dependencies

Additionally, some Python plugins come with a `requirements.txt` which can be
used to install the plugin's dependencies using the `pip` tools:

```bash
pip3 install -r requirements.txt
```

Note: You might need to also specify the `--user` command line flag depending on
your environment.


## More Plugins from the Community

 - [@conscott's plugins](https://github.com/conscott/c-lightning-plugins)
 - [@renepickhardt's plugins](https://github.com/renepickhardt/c-lightning-plugin-collection)
 - [@fiatjaf's plugins](https://github.com/fiatjaf/lightningd-gjson-rpc/tree/master/cmd)
 - [@rsbondi's plugins](https://github.com/rsbondi/clightning-go-plugin)
 - [c-lightning plugins emulating commands of LND (lncli)](https://github.com/kristapsk/c-lightning-lnd-plugins)

## Plugin Builder Resources

 - [Description of the plugin API][plugin-docs]
 - [C Plugin API][c-api] by @rustyrussell
 - [Python Plugin API & RPC Client][python-api] ([PyPI][python-api-pypi]) by @cdecker and [a video tutorial](https://www.youtube.com/watch?v=FYs1I-pCJIg) by @renepickhardt
 - [Go Plugin API & RPC Client][go-api] by @niftynei
 - [C++ Plugin API & RPC Client][cpp-api] by @darosior
 - [Javascript Plugin API & RPC Client][js-api] by @darosior

[esplora]: https://github.com/Blockstream/esplora
[pers-chans]: https://github.com/lightningd/plugins/tree/master/persistent-channels
[probe]: https://github.com/lightningd/plugins/tree/master/probe
[prometheus]: https://github.com/lightningd/plugins/tree/master/prometheus
[summary]: https://github.com/lightningd/plugins/tree/master/summary
[donations]: https://github.com/lightningd/plugins/tree/master/donations
[plugin-docs]: https://lightning.readthedocs.io/PLUGINS.html
[c-api]: https://github.com/ElementsProject/lightning/blob/master/plugins/libplugin.h
[python-api]: https://github.com/ElementsProject/lightning/tree/master/contrib/pylightning
[python-api-pypi]: https://pypi.org/project/pylightning/
[go-api]: https://github.com/niftynei/glightning
[sitzprobe]: https://github.com/niftynei/sitzprobe
[autopilot]: https://github.com/lightningd/plugins/tree/master/autopilot
[rebalance]: https://github.com/lightningd/plugins/tree/master/rebalance
[sendinvoiceless]: https://github.com/lightningd/plugins/tree/master/sendinvoiceless
[graphql]: https://github.com/nettijoe96/c-lightning-graphql
[graphql-spec]: https://graphql.org/
[autoreload]: https://github.com/lightningd/plugins/tree/master/autoreload
[lightning-qt]: https://github.com/darosior/pylightning-qt
[cpp-api]: https://github.com/darosior/lightningcpp
[js-api]: https://github.com/darosior/clightningjs
[monitor]: https://github.com/renepickhardt/plugins/tree/master/monitor
[reckless]: https://github.com/darosior/reckless
[sauron]: https://github.com/lightningd/plugins/tree/master/sauron
[zmq-home]: https://zeromq.org/
[zmq]: https://github.com/lightningd/plugins/tree/master/zmq
[csvexportpays]: https://github.com/0xB10C/c-lightning-plugin-csvexportpays
