# Autopilot

This is a version of Rene Pickhardt's [Autopilot library][lib] ported as a
Core-Lightning plugin.

> :warning: This plugin is still being ported and may not be currently reflect
> the entire functionality. :construction:

## Command line options

The plugin exposes the following new command line options:

 - `--autopilot-percent`: What percentage of funds should be under the
   autopilots control? You may not want the autopilot to manage all of your
   funds, in case you still want to manually open a channel. This parameter
   limits the amount the plugin will use to manage its own channels. Default
   value is 75% of available funds.
 - `--autopilot-num-channels`: How many channels should the autopilot aim for?
   Default is 10 channels overall, including any manually opened channels.
 - `--autopilot-min-channel-size-msat`: Minimum channel size to open. The
   plugin will never open channels smaller than this amount. Default value is
   100000000msat = 1mBTC.
   
## JSON-RPC methods

The plugin also exposes the following methods:

 - `autopilot-run-once`: let's the plugin inspect the current state of
   channels and, if required, will search for candidate peers to open new
   channels with. The optional argument `dryrun` will run the recommendation
   but not actually connect to the peer or open channels.
   
At the time of writing the recommendations may take considerable time and
consume a lot of CPU cycles due to the use of multiple algorithms that are not
tuned to the network's size.


[lib]: https://github.com/ElementsProject/lightning/pull/1888
