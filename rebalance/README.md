# Rebalance plugin

This plugin moves liquidity between your channels using circular payments


## Installation

For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)


## Usage

Once the plugin is installed and active, there are four additional methods for helping to rebalance channels:
1) Either you can call `lightning-cli rebalanceall` to automatically fix all of your channels' liquidity.
2) `lightning-cli rebalancestop` stops the ongoing `rebalanceall`.
3) Or you can call `lightning-cli rebalance outgoing_scid incoming_scid` to rebalance individual channels.
4) `lightning-cli rebalancereport` shows information: plugin settings, past rebalance stats, etc.

## Automatic rebalance

A lightning node usually has multiple channels of different sizes. The node can perform best if all channels have `{enough_liquidity}` for both directions. So the rebalance has multiple purposes with different priority:
1) **The primary goal** is to ensure all channels have `{enough_liquidity}` for both direction, or if a given channel is too small for that, then it has a 50/50 liquidity ratio.
2) **The secondary goal** is to distribute the remaining liquidity evenly between the big channels.
3) For the long run, it is very important **to do this economically**. So the fees of fixing liquidity have to be cheaper than the fees of transaction forwards, which can ruin the liquidity again. (This assumes your node has some rational fee setting.) This way the automatic rebalance can run regularly, and your node can earn more on transaction forwarding than spend for rebalancing.

If the plugin cannot find a cheap enough circular route to rebalancing economically, then it does nothing by default. To not to cause a loss for users.

#### Rebalancing strategy

As a first step, depending on the actual situation, there is a need to get a value of `{enough_liquidity}`. The plugin searches for a maximum possible threshold. For which all channels theoretically can be balanced beyond this threshold. Or smaller than `threshold * 2` channels can be balanced to a 50/50 ratio. `{enough_liquidity}` will be half of this maximum threshold.

The next step is to calculate `{ideal_ratio}` for big channels. Beyond the `{enough_liquidity}` threshold, big channels should share the remaining liquidity evenly, so every big channels' liquidity ratio should be close to the `{ideal_ratio}`.

After we know the current `{enough_liquidity}` threshold and `{ideal_ratio}`, the plugin checks every possible channel pairs to seek a proper rebalance opportunity. If it finds a matching pair, it calls the individual rebalance method for them. If the rebalance fails, the plugin tries again with a lesser amount, until it reaches the minimum rebalancable amount, or the rebalance succeeds.

This process may take a while. Automatic rebalance can run for hours in the background, but you can stop it anytime with `lightning-cli rebalancestop`.

#### Parameters for rebalanceall

- OPTIONAL: The `min_amount` parameter sets the minimum rebalancable amount in millisatoshis. The parameter also can be specified in other denominations by appending a valid suffix, i. e. '1000000sat', '0.01btc' or '10mbtc'. The default value is '50000sat'.
- OPTIONAL: The `feeratio` sets how much the rebalance may cost as a ratio of your default fee. Its default value is `0.5`, which means it can use a maximum of half of your node's default fee.

#### Tips and Tricks for automatic rebalance

- It may work only with well-connected nodes. You should have several different channels to use it with a good chance for success.
- Your node should have some rational default fee setting. If you use cheaper fees than your neighbors, it probably cannot find a cheap enough circular route to rebalance.

## Individual channel rebalance
You can use the `lightning-cli` to rebalance channels like this:

```
lightning-cli rebalance outgoing_scid incoming_scid [msatoshi] [retry_for] [maxfeepercent] [exemptfee] [getroute_method]
```
def rebalance(plugin, outgoing_scid, incoming_scid, msatoshi: Millisatoshi = None,
              retry_for: int = 60, maxfeepercent: float = 0.5,
              exemptfee: Millisatoshi = Millisatoshi(5000),
              getroute_method=None):
If you want to skip/default certain optional parameters but use others, you can
use always the `lightning-cli -k` (key=value) syntax like this:

```bash
lightning-cli rebalance -k outgoing_scid=1514942x51x0 incoming_scid=1515133x10x0 maxfeepercent=1
```

#### Parameters for rebalance

- The `outgoing_scid` is the short_channel_id of the sending channel,
- The `incoming_scid` is the short_channel_id of the receiving channel.
- OPTIONAL: The `msatoshi` parameter sets the amount in milli-satoshis to be
  transferred. If the parameter is left out, the plugin will calucate an amount
  that will balance the channels 50%/50%. The parameter can also be given in
  other denominations by appending i.e. '1000000sat', '0.01btc' or '10mbtc'.
- OPTIONAL: `retry_for` defines the number of seconds the plugin will retry to
  find a suitable route. Default: 60 seconds.
- OPTIONAL: `maxfeepercent` is a perecentage limit of the money to be paid in
  fees and defaults to 0.5.
- OPTIONAL: The `exemptfee` option can be used for tiny payments which would be
  dominated by the fee leveraged by forwarding nodes. Setting `exemptfee`
  allows the `maxfeepercent` check to be skipped on fees that are smaller than
  exemptfee (default: 5000 millisatoshi).
- OPTIONAL: The `getroute_method` option can be for route search can be 'basic'
  or 'iterative'.  
  'basic': Tries all routes sequentially.  
  'iterative': Tries shorter and bigger routes first.


#### Tips and Tricks for individual rebalance

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
