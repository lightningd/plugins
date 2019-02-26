# Summary plugin

This plugin is a little hack to show a summary of your node, including
fiat amounts.

## Options:

* --summary-currency: Currency ticker to look up on bitaverage (default: `USD`)
* --summary-currency-prefix: Prefix when printing currency (default: `USD $`)

## Example Usage

```
$ lightning-cli summary | json_pp
{
   "network" : "TESTNET",
   "utxo_amount" : "1.20119332000btc = USD $4582.22",
   "avail_in" : "2.06940379btc = USD $7894.20",
   "avail_out" : "0.27095103btc = USD $1033.60",
   "my_address" : "031a3478d481b92e3c28810228252898c5f0d82fc4d07f5210c4f34d4aba56b769@165.227.30.200",
   "num_channels" : 31,
   "num_utxos" : 5,
   "num_connected" : 1,
   "num_gossipers" : 32
}
```
