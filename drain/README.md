# Drain and Fill Plugin

This plugin drains or fills up the capacity of one of your channel using
circular payments to yourself. This can be useful for:

- liquidity management
- cleaning up or reducing channels before closing
    - keeping capacity: pushing remaining balance into other lightning channels
    - reducing capacity: filling up a channel before closing to reduce capacity
- accumulating dust before closing multiple channels
- ...

## Installation

This plugin relies on the `pylightning` library. As with most plugins you should
be able to install dependencies with `pip`:

```bash
pip3 install -r requirements.txt
```

You might need to also specify the `--user` command line flag depending on
your environment. If you dont want this and your plugin only uses `pylightning`
as the only dependency, you can also start `lightningd` with the `PYTHONPATH`
environment variable to the `pylightning` package of your `lightningd`
installation. For example:

```
PYTHONPATH=/path/to/lightning.git/contrib/pylightning lightningd --plugin=...
```

## Startup

The plugin can be started with `lightningd` by adding the `--plugin` option.
Remember that all `lightningd` plugins have to have executable permissions.

```
lightningd --plugin=/path/to/plugin/drain.py
```

Alternatively, you can also symlink or copy the plugins executable to the
`.lightning/plugins` folder or the `plugins` folder of your c-lightning
installation as executables within these directories will be loaded as plugins.


## Usage

Once the plugin is active you can use it to `drain` liquidity on one of your
channels by:

```
lightning-cli drain scid [percentage] [chunks] [maxfeepercent] [retry_for] [exemptfee]
```

The plugin has also a `fill` command that does excactly the opposite. You
can use it to fill up your side of the channel:

```
lightning-cli fill scid [percentage] [chunks] [maxfeepercent] [retry_for] [exemptfee]
```

### Parameters

- The `scid` is the short_channel_id of the channel to drain or fill.
- OPTIONAL: The `percentage` paramter tells the plugin how much of the channel
  capacity should be drained/filled. Default: 100. Likewise a 'drain 50' will
  balance a channel that is above 50% of its capacity same as 'fill 50' will
  balance a channel that is below 50% of its capacity.
- OPTIONAL: The `chunks` parameter tells the plugin to try breaking down the
  payment into several smaller ones. In this case it may happen that the
  operation will only be partially completed. The parameters value is the
  number of chunks to use. Default: auto-detect based on capacities, max 16.
- OPTIONAL: `maxfeepercent` is a perecentage limit of the money to be paid in
  fees and defaults to 0.5.
- OPTIONAL: `retry_for` defines the number of seconds the plugin will retry to
  find a suitable route. Default: 60 seconds. Note: Applies for each chunk.
- OPTIONAL: The `exemptfee` option can be used for tiny payments which would be
  dominated by the fee leveraged by forwarding nodes. Setting `exemptfee`
  allows the `maxfeepercent` check to be skipped on fees that are smaller than
  exemptfee (default: 5000 millisatoshi).

NOTE: The `percentage` relates to resulting target capacity. A 'drain 1%' will
      not try to send 1% of channel balance away, but try to reduce its balance
      to 'just' 99%, if channel is above 99% total capacity.

NOTE: Automatically converting a 'drain 70' to a 'fill 30' if the channel is
      already below 30% capacity is not implemented yet.


## Tips and Tricks

- To find the correct channel IDs, you can use the `summary` plugin which can
  be found [here](https://github.com/lightningd/plugins/tree/master/summary).
- After some failed attempts, may worth checking the `lightningd` logs for
  further information.
- Channels have a `channel_reserve_satoshis` value, which is usually 1% of the
  channel's total balance. Initially, this reserve may not be met, as only one
  side has funds; but the protocol ensures that there is always progress toward
  meeting this reserve, and once met, [it is maintained.](https://github.com/lightningnetwork/lightning-rfc/blob/master/02-peer-protocol.md#rationale)
  Therefore you cannot drain or fill a channel to be completely empty or full.
