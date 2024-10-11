# Prometheus plugin for c-lightning

This plugin exposes some key metrics from c-lightning in the prometheus format
so it can be scraped, plotted and alerts can be created on it. The plugin adds
the following command line arguments:

 - `prometheus-listen`: the IP address and port to bind the HTTP server to
   (default: `127.0.0.1:9750`)

Exposed variables include:

 - `node`: ID, version, ...
 - `peers`: whether they are connected, and how many channels are currently
   open
 - `channels`: fund allocations, spendable funds, and how many unresolved
   HTLCs are currently attached to the channel
 - `funds`: satoshis in on-chain outputs, satoshis allocated to channels and
   total sum (may be inaccurate during channel resolution).
