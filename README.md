# Plugins for c-lightning

Community curated plugins for c-lightning.


## Available plugins

| Name                               | Short description                                                          |
|------------------------------------|----------------------------------------------------------------------------|
| [autopilot][autopilot]             | An autopilot that suggests channels that should be established             |
| [autoreload][autoreload]           | A developer plugin that reloads a plugin under development when it changes |
| [donations][donations]             | A simple donations page to accept donations from the web                   |
| [graphql][graphql]                 | Exposes the c-lightning API over [graphql][graphql-spec]                   |
| [lightning-qt][lightning-qt]       | A bitcoin-qt-like GUI for lightningd                                       |
| [persistent-channels][pers-chans]  | Maintains a number of channels to peers                                    |
| [probe][probe]                     | Regularly probes the network for stability                                 |
| [prometheus][prometheus]           | Lightning node exporter for the prometheus timeseries server               |
| [rebalance][rebalance]             | Keeps your channels balanced                                               |
| [sendinvoiceless][sendinvoiceless] | Sends some money without an invoice from the receiving node.               |
| [sitzprobe][sitzprobe]             | A Lightning Network payment rehearsal utility                              |
| [summary][summary]                 | Print a nice summary of the node status                                    |


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

### Pylightning

All python plugins depend on the `pylightning` library. It can be given in
several ways:

 - Using `pip` tools: `pip3 install pylightning`
 - Using the `PYTHONPATH` environment variable to include your clightning's
   shipped `pylightning` library:

```bash
PYTHONPATH=/path/to/lightnind/contrib/pylightning lightningd
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

 - https://github.com/conscott/c-lightning-plugins
 - https://github.com/renepickhardt/c-lightning-plugin-collection

## Plugin Builder Resources

 - [Description of the plugin API][plugin-docs]
 - [C Plugin API][c-api] by @rustyrussell
 - [Python Plugin API & RPC Client][python-api] ([PyPI][python-api-pypi]) by @cdecker and [a video tutorial](https://www.youtube.com/watch?v=FYs1I-pCJIg) by @renepickhardt
 - [Go Plugin API & RPC Client][go-api] by @niftynei

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
