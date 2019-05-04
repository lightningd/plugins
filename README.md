# Plugins for c-lightning

Community curated plugins for c-lightning.

To install and activate a plugin you need to stop your lightningd and restart it with the `plugin` argument like this:

```
lightningd --plugin=/path/to/plugin/directory/plugin_file_name.py
```

where the `plugin_file_name.py` should be an executable (`chmod a+x plugin_file_name.py`) file and can be written in any programming language.

## Available plugins

| Name                              | Short description                                              |
|-----------------------------------|----------------------------------------------------------------|
| [autopilot][autopilot]            | An autopilot that suggests channels that should be established |
| [donations][donations]            | A simple donations page to accept donations from the web       |
| [graphql][graphql]                | Exposes the c-lightning API over [graphql][graphql-spec]       |
| [persistent-channels][pers-chans] | Maintains a number of channels to peers                        |
| [probe][probe]                    | Regularly probes the network for stability                     |
| [prometheus][prometheus]          | Lightning node exporter for the prometheus timeseries server   |
| [rebalance][rebalance]            | Keeps your channels balanced                                   |
| [sendinvoiceless][sendinvoiceless]| Sends some money without an invoice from the receiving node.   |
| [sitzprobe][sitzprobe]            | A Lightning Network payment rehearsal utility                  |
| [summary][summary]                | Print a nice summary of the node status                        |


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
