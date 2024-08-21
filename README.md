# Plugins for Core-Lightning

Community curated plugins for Core-Lightning.

[![Integration Tests (latest)](https://github.com/lightningd/plugins/actions/workflows/main.yml/badge.svg)](https://github.com/lightningd/plugins/actions/workflows/main.yml)
[![Nightly Integration Tests (master)](https://github.com/lightningd/plugins/actions/workflows/nightly.yml/badge.svg)](https://github.com/lightningd/plugins/actions/workflows/nightly.yml)

## Available plugins

| Name                                 | Short description                                                                           | CLN<br>`23.11`/`24.02`/`24.05`/`master` |
| ------------------------------------ | ------------------------------------------------------------------------------------------- | :----: |
| [backup][backup]                     | A simple and reliable backup plugin                                                         | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbackup_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbackup_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbackup_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbackup_nightly.json) |
| [bolt12-prism][bolt12-prism]         | Split payments triggered manually or by paying a BOLT 12                                    | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbolt12-prism_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbolt12-prism_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbolt12-prism_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbolt12-prism_nightly.json) |
| [btcli4j][btcli4j]                   | A Bitcoin Backend to enable safely the pruning mode, and support also rest APIs.            | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbtcli4j_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbtcli4j_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbtcli4j_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fbtcli4j_nightly.json) |
| [circular][circular]                 | A smart rebalancing plugin for Core Lightning routing nodes                                 | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcircular_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcircular_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcircular_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcircular_nightly.json) |
| [clearnet][clearnet]                 | A plugin that can be used to enforce clearnet connections when possible                     | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fclearnet_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fclearnet_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fclearnet_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fclearnet_nightly.json) |
| [cln-ntfy][cln-ntfy]                 | Core Lightning plugin for sending `ntfy` alerts.                                            | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcln-ntfy_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcln-ntfy_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcln-ntfy_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcln-ntfy_nightly.json) |
| [clnrod][clnrod]                     | Channel acceptor plugin. Configurable with external data from amboss/1ml and notifications  | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fclnrod_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fclnrod_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fclnrod_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fclnrod_nightly.json) |
| [currencyrate][currencyrate]         | A plugin to convert other currencies to BTC using web requests                              | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcurrencyrate_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcurrencyrate_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcurrencyrate_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fcurrencyrate_nightly.json) |
| [datastore][datastore]               | The Datastore Plugin                                                                        | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fdatastore_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fdatastore_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fdatastore_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fdatastore_nightly.json) |
| [donations][donations]               | A simple donations page to accept donations from the web                                    | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fdonations_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fdonations_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fdonations_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fdonations_nightly.json) |
| [event-websocket][c-lightning-events]   | Exposes notifications over a Websocket                                                      | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fc-lightning-events_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fc-lightning-events_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fc-lightning-events_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fc-lightning-events_nightly.json) |
| [feeadjuster][feeadjuster]           | Dynamic fees to keep your channels more balanced                                            | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ffeeadjuster_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ffeeadjuster_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ffeeadjuster_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ffeeadjuster_nightly.json) |
| [go-lnmetrics.reporter][reporter]    | Collect and report of the lightning node metrics                                            | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fgo-lnmetrics.reporter_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fgo-lnmetrics.reporter_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fgo-lnmetrics.reporter_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fgo-lnmetrics.reporter_nightly.json) |
| [graphql][graphql]                   | Exposes the Core-Lightning API over [graphql][graphql-spec]                                 | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fgraphql_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fgraphql_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fgraphql_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fgraphql_nightly.json) |
| [holdinvoice][holdinvoice]           | Holds htlcs for invoices until settle or cancel is called (aka Hodlinvoices) via RPC/GRPC   | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fholdinvoice_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fholdinvoice_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fholdinvoice_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fholdinvoice_nightly.json) |
| [invoice-queue][Lightning-Invoice-Queue]       | Listen to lightning invoices from multiple nodes and send to a redis queue for processing   | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2FLightning-Invoice-Queue_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2FLightning-Invoice-Queue_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2FLightning-Invoice-Queue_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2FLightning-Invoice-Queue_nightly.json) |
| [lightning-qt][lightning-qt]         | A bitcoin-qt-like GUI for lightningd                                                        | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Flightning-qt_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Flightning-qt_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Flightning-qt_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Flightning-qt_nightly.json) |
| [listmempoolfunds][listmempoolfunds] | Track unconfirmed wallet deposits                                                           | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Flistmempoolfunds_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Flistmempoolfunds_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Flistmempoolfunds_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Flistmempoolfunds_nightly.json) |
| [ln-address-pay][ln-address-pay]     | Allows payments to lightning addresses                                                      | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fln-address-pay_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fln-address-pay_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fln-address-pay_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fln-address-pay_nightly.json) |
| [monitor][monitor]                   | helps you analyze the health of your peers and channels                                     | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fmonitor_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fmonitor_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fmonitor_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fmonitor_nightly.json) |
| [nloop][NLoop]                       | Generic Lightning Loop for boltz                                                            | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2FNLoop_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2FNLoop_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2FNLoop_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2FNLoop_nightly.json) |
| [paythrough][paythrough]             | Pay an invoice through a specific channel, regardless of better routes                      | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fpaythrough_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fpaythrough_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fpaythrough_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fpaythrough_nightly.json) |
| [persistent-channels][pers-chans]    | Maintains a number of channels to peers                                                     | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fpersistent-channels_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fpersistent-channels_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fpersistent-channels_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fpersistent-channels_nightly.json) |
| [poncho][poncho]                     | Turns CLN into a [hosted channels][blip12] provider                                         | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fponcho_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fponcho_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fponcho_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fponcho_nightly.json) |
| [pruning][c-lightning-pruning-plugin]                   | This plugin manages pruning of bitcoind such that it can always sync                        | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fc-lightning-pruning-plugin_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fc-lightning-pruning-plugin_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fc-lightning-pruning-plugin_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fc-lightning-pruning-plugin_nightly.json) |
| [rebalance][rebalance]               | Keeps your channels balanced                                                                | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Frebalance_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Frebalance_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Frebalance_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Frebalance_nightly.json) |
| [sauron][sauron]                     | A Bitcoin backend relying on [Esplora][esplora]'s API                                       | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsauron_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsauron_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsauron_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsauron_nightly.json) |
| [sitzprobe][sitzprobe]               | A Lightning Network payment rehearsal utility                                               | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsitzprobe_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsitzprobe_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsitzprobe_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsitzprobe_nightly.json) |
| [sling][sling]                       | Rebalance your channels with smart rules and built-in background tasks                      | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsling_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsling_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsling_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsling_nightly.json) |
| [summars][summars]                   | Print configurable summary of node, channels and optionally forwards, invoices, payments    | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsummars_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsummars_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsummars_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fsummars_nightly.json) |
| [torq-plugin][torq-plugin]           | Better CLN integration into [Torq](https://github.com/lncapital/torq)                       | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ftorq-plugin_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ftorq-plugin_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ftorq-plugin_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ftorq-plugin_nightly.json) |
| [trustedcoin][trustedcoin]           | Replace your Bitcoin Core with data from public block explorers                             | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ftrustedcoin_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ftrustedcoin_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ftrustedcoin_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Ftrustedcoin_nightly.json) |
| [watchtower-client][watchtower-client]      | Watchtower client for The Eye of Satoshi                                                    | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fwatchtower-client_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fwatchtower-client_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fwatchtower-client_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fwatchtower-client_nightly.json) |
| [webhook][webhook]                   | Dispatches webhooks based from [event notifications][event-notifications]                   | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fwebhook_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fwebhook_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fwebhook_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fwebhook_nightly.json) |
| [zmq][zmq]                           | Publishes notifications via [ZeroMQ][zmq-home] to configured endpoints                      | ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fzmq_23.11.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fzmq_24.02.2.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fzmq_24.05.json) ![](https://img.shields.io/endpoint?url=https%3A%2F%2Flightningd.github.io%2Fplugins%2F.badges%2Fzmq_nightly.json) |

## Plugin Managers

This is a list of plugin managers that can help you install these plugins:

| Name                                 | Short description                                                                           |
| ------------------------------------ | ------------------------------------------------------------------------------------------- |
| [coffee][coffee]                     | Reference implementation for a flexible core lightning plugin manager                       |
| [reckless][reckless]                 | Comes with CLN. Reckless currently supports python and javascript plugins.                  |

## Archived plugins

If you can't find a plugin you're looking for, it may have been [archived](archived.md). Plugins are archived when they start to fail integration testing with the latest CLN release, at which point they will be considered unmaintained.

## Installation

To install and activate a plugin you need to stop your lightningd and restart it
with the `plugin` argument like this:

```
lightningd --plugin=/path/to/plugin/directory/plugin_file_name.py
```

Notes:
 - The `plugin_file_name.py` must have executable permissions:
   `chmod a+x plugin_file_name.py`
   - You must have git core.fileMode set to true to reflect the permissions in git
   - On Windows you might need to do the _git add_ command in WSL to be able to change the permissions
 - A plugin can be written in any programming language, as it interacts with
   `lightningd` purely using stdin/stdout pipes.

### Automatic plugin initialization

Alternatively, especially when you use multiple plugins, you can copy or symlink
all plugin directories into your `~/.lightning/plugins` directory. The daemon
will load each executable it finds in sub-directories as a plugin. In this case
you don't need to manage all the `--plugin=...` parameters.

### Dynamic plugin initialization

Most of the plugins can be managed using the RPC interface. Use
```
lightning-cli plugin start /path/to/plugin/directory/plugin_file_name
```
to start it, and
```
lightning-cli plugin stop /path/to/plugin/directory/plugin_file_name
```
to stop it.

As a plugin developer this option is configurable with all the available plugin libraries,
and defaults to `true`.


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
Core-Lightning.

Writing a test is as simple as this:

- The framework will look for unittest filenames starting with `test_`.
- The test functions should also start with `test_`.

```python
from pyln.testing.fixtures import *

pluginopt = {'plugin': os.path.join(os.path.dirname(__file__), "YOUR_PLUGIN.py")}

def test_your_plugin(node_factory, bitcoind):
    l1 = node_factory.get_node(options=pluginopt)
    s = l1.rpc.getinfo()
    assert(s['network'] == 'regtest') # or whatever you want to test
```

Tests are run against pull requests, all commits on `master`, as well as once
ever 24 hours to test against the latest `master` branch of the Core-Lightning
development tree.

Running tests locally can be done like this:
(make sure the `PYTHONPATH` env variable is correct)

```bash
pytest YOUR_PLUGIN/YOUR_TEST.py
```

### Python plugins specifics

#### Additional dependencies

Additionally, some Python plugins come with a `requirements.txt` which can be
used to install the plugin's dependencies using the `pip` tools:

```bash
pip3 install -r requirements.txt
```

Note: You might need to also specify the `--user` command line flag depending on
your environment.

#### Minimum supported Python version

The minimum supported version of Python for this repository is currently `3.8.x` (14 Oct 2019).
Python plugins users must ensure to have a version `>= 3.8`.
Python plugins developers must ensure their plugin to work with all Python versions `>= 3.8`.


## More Plugins from the Community

 - [@conscott's plugins](https://github.com/conscott/c-lightning-plugins)
 - [@renepickhardt's plugins](https://github.com/renepickhardt/c-lightning-plugin-collection)
 - [@rsbondi's plugins](https://github.com/rsbondi/clightning-go-plugin)
 - [Core-Lightning plugins emulating commands of LND (lncli)](https://github.com/kristapsk/c-lightning-lnd-plugins)

## Plugin Builder Resources

 - [Description of the plugin API][plugin-docs]
 - [C Plugin API][c-api] by @rustyrussell
 - [Python Plugin API & RPC Client][python-api] ([PyPI][python-api-pypi]) by @cdecker and [a video tutorial](https://www.youtube.com/watch?v=FYs1I-pCJIg) by @renepickhardt
 - [Go Plugin API & RPC Client][go-api] by @niftynei
 - [C++ Plugin API & RPC Client][cpp-api] by @darosior
 - [Javascript Plugin API & RPC Client][js-api] by @darosior
 - [TypeScript Plugin API & RPC Client][ts-api] by @AaronDewes
 - [Java Plugin API & RPC Client][java-api] by @vincenzopalazzo
 - [C# Plugin Guideline and example project][csharp-example] by @joemphilips
 - [Kotlin plugin guideline and example][kotlin-example] by @vincenzopalazzo

[backup]: https://github.com/lightningd/plugins/tree/master/backup
[blip12]: https://github.com/lightning/blips/blob/42cec1d0f66eb68c840443abb609a5a9acb34f8e/blip-0012.md
[bolt12-prism]: https://github.com/gudnuf/bolt12-prism
[btcli4j]: https://github.com/clightning4j/btcli4j
[c-api]: https://github.com/ElementsProject/lightning/blob/master/plugins/libplugin.h
[c-lightning-events]: https://github.com/rbndg/c-lightning-events
[c-lightning-pruning-plugin]: https://github.com/Start9Labs/c-lightning-pruning-plugin
[circular]: https://github.com/giovannizotta/circular
[clearnet]: https://github.com/lightningd/plugins/tree/master/clearnet
[cln-ntfy]: https://github.com/yukibtc/cln-ntfy
[clnrod]: https://github.com/daywalker90/clnrod
[coffee]: https://github.com/coffee-tools/coffee
[cpp-api]: https://github.com/darosior/lightningcpp
[csharp-example]: https://github.com/joemphilips/DotNetLightning/tree/master/examples/HelloWorldPlugin
[currencyrate]: https://github.com/lightningd/plugins/tree/master/currencyrate
[datastore]: https://github.com/lightningd/plugins/tree/master/datastore
[donations]: https://github.com/lightningd/plugins/tree/master/donations
[esplora]: https://github.com/Blockstream/esplora
[event-notifications]: https://lightning.readthedocs.io/PLUGINS.html#event-notifications
[feeadjuster]: https://github.com/lightningd/plugins/tree/master/feeadjuster
[go-api]: https://github.com/niftynei/glightning
[graphql]: https://github.com/nettijoe96/c-lightning-graphql
[graphql-spec]: https://graphql.org/
[holdinvoice]: https://github.com/daywalker90/holdinvoice
[java-api]: https://github.com/clightning4j/JRPClightning
[js-api]: https://github.com/lightningd/clightningjs
[kotlin-example]: https://vincenzopalazzo.medium.com/a-day-in-a-c-lightning-plugin-with-koltin-c8bbd4fa0406
[Lightning-Invoice-Queue]: https://github.com/rbndg/Lightning-Invoice-Queue
[lightning-qt]: https://github.com/darosior/pylightning-qt
[listmempoolfunds]: https://github.com/andrewtoth/listmempoolfunds
[ln-address-pay]: https://github.com/nosedam/ln-address-pay
[monitor]: https://github.com/renepickhardt/plugins/tree/master/monitor
[NLoop]: https://github.com/bitbankinc/NLoop
[paythrough]: https://github.com/andrewtoth/paythrough
[pers-chans]: https://github.com/lightningd/plugins/tree/master/persistent-channels
[plugin-docs]: https://docs.corelightning.org/docs/plugin-development
[poncho]: https://github.com/fiatjaf/poncho
[python-api]: https://github.com/ElementsProject/lightning/tree/master/contrib/pylightning
[python-api-pypi]: https://pypi.org/project/pylightning/
[rebalance]: https://github.com/lightningd/plugins/tree/master/rebalance
[reckless]: https://docs.corelightning.org/reference/reckless
[reporter]: https://github.com/LNOpenMetrics/go-lnmetrics.reporter
[sauron]: https://github.com/lightningd/plugins/tree/master/sauron
[sitzprobe]: https://github.com/niftynei/sitzprobe
[sling]: https://github.com/daywalker90/sling
[summars]: https://github.com/daywalker90/summars
[torq-plugin]: https://github.com/lncapital/torq-cln-plugin
[trustedcoin]: https://github.com/fiatjaf/trustedcoin
[ts-api]: https://github.com/runcitadel/c-lightning.ts
[watchtower-client]: https://github.com/talaia-labs/rust-teos/tree/master/watchtower-plugin
[webhook]: https://github.com/fiatjaf/lightningd-webhook
[zmq]: https://github.com/lightningd/plugins/tree/master/zmq
[zmq-home]: https://zeromq.org/
