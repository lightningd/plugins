## Archived plugins

The following is a list of archived plugins that are no longer maintained and reside inside the 'archived' subdirectory.
Any plugins that fail CI will be archived.

If you like a plugin from that list, feel free to update and fix it, so we can un-archive it.

| Name                                 | Short description                                                                           |
| ------------------------------------ | ------------------------------------------------------------------------------------------- |
| [autopilot][autopilot]               | An autopilot that suggests channels that should be established                              |
| [balance-AMP-pay][bal-amp-pay]       | Computes an optimal split of a payment amount for the use of AMP. Helps keep funds balanced |
| [btcli4j][btcli4j]                   | A Bitcoin Backend to enable safely the pruning mode, and support also rest APIs.            |
| [circular][circular]                 | A smart rebalancing plugin for Core Lightning routing nodes                                 |
| [clnrest-rs][clnrest-rs]             | Drop-in rust implementation of CLN's clnrest.py, shipped with CLN since v25.02              |
| [commando][commando]                 | This plugin allows to send commands between nodes                                           |
| [datastore][datastore]               | The Datastore Plugin                                                                        |
| [drain][drain]                       | Draining, filling and balancing channels with automatic chunks.                             |
| [event-websocket][c-lightning-events]| Exposes notifications over a Websocket                                                      |
| [fixroute][fixroute]                 | Constructs a route object (using sendpay) which goes over a sequence of node ids            |
| [go-lnmetrics.reporter][reporter]    | Collect and report of the lightning node metrics                                            |
| [graphql][graphql]                   | Exposes the Core-Lightning API over [graphql][graphql-spec]                                 |
| [helpme][helpme]                     | This plugin is designed to walk you through setting up a fresh Core-Lightning node          |
| [historian][historian]               | Archiving the Lightning Network                                                             |
| [holdinvoice][holdinvoice]           | Holds htlcs for invoices until settle or cancel is called (aka Hodlinvoices) via RPC/GRPC   |
| [invoice-queue][Lightning-Invoice-Queue]       | Listen to lightning invoices from multiple nodes and send to a redis queue for processing   |
| [jitrebalance][jitrebalance]         | The JITrebalance plugin                                                                     |
| [lightning-qt][lightning-qt]         | A bitcoin-qt-like GUI for lightningd                                                        |
| [listmempoolfunds][listmempoolfunds] | Track unconfirmed wallet deposits                                                           |
| [nloop][NLoop]                       | Generic Lightning Loop for boltz                                                            |
| [noise][noise]                       | Chat with your fellow node operators                                                        |
| [nostr-control][nostr-control]       | Allows you to talk to your node oand send you events from your node over nostr DMs          |
| [paytest][paytest]                   | A plugin to benchmark the performance of the ~pay~ plugin                                   |
| [paythrough][paythrough]             | Pay an invoice through a specific channel, regardless of better routes                      |
| [poncho][poncho]                     | Turns CLN into a [hosted channels][blip12] provider                                         |
| [probe][probe]                       | Regularly probes the network for stability                                                  |
| [pruning][c-lightning-pruning-plugin]| This plugin manages pruning of bitcoind such that it can always sync                        |
| [sitzprobe][sitzprobe]               | A Lightning Network payment rehearsal utility                                               |
| [spark-commando][spark-commando]     | Heavily inspired by Rusty's commando plugin                                                 |
| [sparko][sparko]                     | RPC over HTTP with fine-grained permissions, SSE and spark-wallet support                   |
| [webhook][webhook]                   | Dispatches webhooks based from [event notifications][event-notifications]                   |

[autopilot]: https://github.com/lightningd/plugins/tree/master/archived/autopilot
[bal-amp-pay]: https://github.com/renepickhardt/plugins/tree/balanced_pay/balanced_amp_payments
[blip12]: https://github.com/lightning/blips/blob/42cec1d0f66eb68c840443abb609a5a9acb34f8e/blip-0012.md
[btcli4j]: https://github.com/clightning4j/btcli4j
[c-lightning-events]: https://github.com/rbndg/c-lightning-events
[c-lightning-pruning-plugin]: https://github.com/Start9Labs/c-lightning-pruning-plugin
[circular]: https://github.com/giovannizotta/circular
[clnrest-rs]: https://github.com/daywalker90/clnrest-rs
[commando]: https://github.com/lightningd/plugins/tree/master/archived/commando
[datastore]: https://github.com/lightningd/plugins/tree/master/archived/datastore
[drain]: https://github.com/lightningd/plugins/tree/master/archived/drain
[event-notifications]: https://lightning.readthedocs.io/PLUGINS.html#event-notifications
[fixroute]: https://github.com/renepickhardt/plugins/tree/fixroute/fixroute
[graphql]: https://github.com/nettijoe96/c-lightning-graphql
[graphql-spec]: https://graphql.org/
[helpme]: https://github.com/lightningd/plugins/tree/master/archived/helpme
[historian]: https://github.com/lightningd/plugins/tree/master/archived/historian
[holdinvoice]: https://github.com/daywalker90/holdinvoice
[jitrebalance]: https://github.com/lightningd/plugins/tree/master/archived/jitrebalance
[Lightning-Invoice-Queue]: https://github.com/rbndg/Lightning-Invoice-Queue
[lightning-qt]: https://github.com/darosior/pylightning-qt
[listmempoolfunds]: https://github.com/andrewtoth/listmempoolfunds
[NLoop]: https://github.com/bitbankinc/NLoop
[noise]: https://github.com/lightningd/plugins/tree/master/archived/noise
[nostr-control]: https://github.com/joelklabo/plugins/tree/nostr-control
[paytest]: https://github.com/lightningd/plugins/tree/master/archived/paytest
[paythrough]: https://github.com/andrewtoth/paythrough
[poncho]: https://github.com/fiatjaf/poncho
[probe]: https://github.com/lightningd/plugins/tree/master/archived/probe
[reporter]: https://github.com/LNOpenMetrics/go-lnmetrics.reporter
[sitzprobe]: https://github.com/niftynei/sitzprobe
[spark-commando]: https://github.com/adi2011/plugins/tree/master/spark-commando
[sparko]: https://github.com/fiatjaf/sparko
[webhook]: https://github.com/fiatjaf/lightningd-webhook
