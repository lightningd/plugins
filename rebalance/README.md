# Rebalance plugin

This plugin moves liquidity between your channels using circular payments.

The plugin can be started with `lightningd` by adding the following `--plugin`
option. As with any `lightningd` plugin, the file has to be executable. As
with any lightning python plugin, `pylightning` must be installed or in your
`PYTHONPATH` environment variable.

```
lightningd --plugin=/path/to/plugins/rebalance.py
```

Once the plugin is active you can rebalance your channels liquidity by running:

```
lightning-cli rebalance outgoing_scid incoming_scid [msatoshi] [maxfeepercent] [retry_for] [exemptfee]
```


## Parameters

 - The `outgoing_scid` is the short_channel_id of the sending channel,
 - The `incoming_scid` is the short_channel_id of the receiving channel.
 - OPTIONAL: The `msatoshi` parameter sets the amount in milli-satoshis to be
   transferred. If the parameter is left out, the plugin will calucate an amount
   that will balance the channels 50%/50%. The parameter can also be given in
   other denominations by appending i.e. '10000sat' or '0.01btc'.
 - OPTIONAL: `maxfeepercent` is a perecentage limit of the money to be paid in
   fees and defaults to 0.5.
 - OPTIONAL: `retry_for` defines the number of seconds the plugin will retry to
   find a suitable route. Default: 60 seconds.
 - OPTIONAL: The `exemptfee` option can be used for tiny payments which would be
   dominated by the fee leveraged by forwarding nodes. Setting `exemptfee`
   allows the `maxfeepercent` check to be skipped on fees that are smaller than
   exemptfee (default: 5000 millisatoshi).


## Tips and Tricks

- To find the correct channel IDs, you can use the `summary` plugin which can
  be found [here](https://github.com/lightningd/plugins/tree/master/summary).
- The ideal amount is not too big, but not too small: it is difficult to find a
  route for a big payment, however some node refuses to forward too small
  amounts (i.e. less than a thousand msatoshi).
- After some failed attempts, may worth checking the `lightningd` logs for
  further information.
- Channels have a `channel_reserve_satoshis` value, which is usually 1% of the
  channel's total balance. Initially, this reserve may not be met, as only one
  side has funds; but the protocol ensures that there is always progress toward
  meeting this reserve, and once met, [it is maintained.](https://github.com/lightningnetwork/lightning-rfc/blob/master/02-peer-protocol.md#rationale)
  Therefore you cannot rebalance a channel to be completely empty or full.
