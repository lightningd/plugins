# Rebalance plugin

This plugin helps to move some msatoshis between your channels using circular payments.

The plugin can be started with `lightningd` by adding the following `--plugin` option
(adjusting the path to wherever the plugins are actually stored):

```
lightningd --plugin=/path/to/plugins/rebalance.py
```

Once the plugin is active you can rebalance your channels liquidity by running:
`lightning-cli rebalance outgoing_channel_id incoming_channel_id msatoshi [maxfeepercent] [retry_for] [exemptfee]`

The `outgoing_channel_id` is the short_channel_id of the sending channel, `incoming_channel_id` is the id of the
receiving channel. The `maxfeepercent` limits the money paid in fees and defaults to 0.5. The maxfeepercent' is a
percentage of the amount that is to be paid. The `exemptfee` option can be used for tiny payments which would be
dominated by the fee leveraged by forwarding nodes. Setting exemptfee allows the maxfeepercent check to be skipped
on fees that are smaller than exemptfee (default: 5000 millisatoshi).

The command will keep finding routes and retrying the payment until it succeeds, or the given `retry_for` seconds
pass. retry_for defaults to 60 seconds and can only be an integer.

### Tips and Tricks ###
- The ideal amount is not too big, but not too small: it is difficult to find a route for a big payment, however
some node refuses to forward too small amounts (i.e. less than a thousand msatoshi).
- After some failed attempts, may worth checking the `lightningd` logs for further information.
- Channels have a `channel_reserve_satoshis` value, which is usually 1% of the channel's total balance. Initially,
this reserve may not be met, as only one side has funds; but the protocol ensures that there is always progress
toward meeting this reserve, and once met, [it is
maintained.](https://github.com/lightningnetwork/lightning-rfc/blob/master/02-peer-protocol.md#rationale)
Therefore you cannot rebalance a channel to be completely empty or full.
