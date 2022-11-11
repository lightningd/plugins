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

This plugin relies on the `pyln-client` library. As with most plugins you should
be able to install dependencies with `pip`:

```bash
pip3 install -r requirements.txt
```

You might need to also specify the `--user` command line flag depending on
your environment. If you dont want this and your plugin only uses `pyln-client`
as the only dependency, you can also start `lightningd` with the `PYTHONPATH`
environment variable to the `pyln-client` package of your `lightningd`
installation, for example:

```
PYTHONPATH=/home/user/lightning.git/contrib/pyln-client lightningd --plugin=...
```

## Startup

The plugin can be started with `lightningd` by adding the `--plugin` option.
Remember that all `lightningd` plugins have to have executable permissions.

```
lightningd --plugin=/path/to/plugin/drain.py
```

Alternatively, you can also symlink or copy the plugins executable to the
`.lightning/plugins` folder or the `plugins` folder of your Core-Lightning
installation as executables within these directories will be loaded as plugins.


## Usage

Once the plugin is active you can use it to `drain` a given percentage of
liquidity (default 100%) on one of your channels by:

```
lightning-cli drain scid [percentage] [chunks] [retry_for] [maxfeepercent] [exemptfee]
```

The plugin has also a `fill` command that does excactly the opposite. You
can use it to fill up a given percentage of liquidity (default 100%) on your
side of a channel:

```
lightning-cli fill scid [percentage] [chunks] [retry_for] [maxfeepercent] [exemptfee]
```

Another useful command is the `setbalance` that will fill up or drain your side
of a channels balance to a given total percentage (default 50%). It will do all
the math for you, so that you do not need to care for current channel balance:

```
lightning-cli setbalance scid [percentage] [chunks] [retry_for] [maxfeepercent] [exemptfee]
```



### Parameters

- The `scid` is the short_channel_id of the channel to drain or fill.
- OPTIONAL: The `percentage` parameter tells the plugin how much of a channels
  total capacity should be `drain`ed or `fill`ed (default: 100%).
  For the `setbalance` command this sets the target percentage and it defaults
  to 50% in this case. Resulting over or under capacity will be limited
  to 100% (full) or 0% (empty) automatically. Examples:
  - A 'drain 10' will send out 10% of the channels total (not current) capacity.
  - A 'drain 100' will send out 100% of the channels total capacity, the channel
  will be empty after this.
  - A 'fill 10' will increase your side of a channels balance by 10% from total.
  - A 'fill 100' will increase will fill up your channel.
  - A 'setbalance' will balance out a channel.
  - A 'setbalance 70' will bring a channel in a state where your side will hold
    70% of total capacity.
- OPTIONAL: The `chunks` parameter tells the plugin to try breaking down the
  payment into several smaller ones. In this case it may happen that the
  operation will only be partially completed. The parameters value is the
  number of chunks to use. Default: auto-detect based on capacities, max 16.
- OPTIONAL: `retry_for` defines the number of seconds the plugin will retry to
  find a suitable route. Default: 60 seconds. Note: Applies for each chunk.
- OPTIONAL: `maxfeepercent` is a percentage limit of the money to be paid in
  fees and defaults to 0.5.
- OPTIONAL: The `exemptfee` option can be used for tiny payments which would be
  dominated by the fee leveraged by forwarding nodes. Setting `exemptfee`
  allows the `maxfeepercent` check to be skipped on fees that are smaller than
  exemptfee (default: 5000 millisatoshi).


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


## TODOs
 - fix: use hook instead of waitsendpay to prevent race conditions
 - fix: occasionally strange route errors. maybe try increasing chunks on route errors.
 - feat: set HTLC_FEE MIN/MAX/STP by feerate
 - chore: reconsider use of listchannels
