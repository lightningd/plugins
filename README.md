# Plugins for c-lightning

Community curated plugins for c-lightning.

## Available plugins

| Name                              | Short description                                            |
|-----------------------------------|--------------------------------------------------------------|
| [donations][donations]            | A simple donations page to accept donations from the web     |
| [persistent-channels][pers-chans] | Maintains a number of channels to peers                      |
| [probe][probe]                    | Regularly probes the network for stability                   |
| [prometheus][prometheus]          | Lightning node exporter for the prometheus timeseries server |
| [sitzprobe][sitzprobe]            | A Lightning Network payment rehearsal utility                |
| [summary][summary]                | Print a nice summary of the node status                      |


## More Plugins from the Community

 - https://github.com/conscott/c-lightning-plugins

## Plugin Builder Resources

 - [Description of the plugin API][plugin-docs]
 - [C Plugin API][c-api] by @rustyrussell
 - [Python Plugin API & RPC Client][python-api] ([PyPI][python-api-pypi]) by @cdecker
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
[sitzprobe]: https://github.com/lightningd/plugins/tree/master/sitzprobe
