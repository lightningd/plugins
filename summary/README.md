# Summary plugin

This plugin is a little hack to show a summary of your node, including
fiat amounts.

## Options:

* --summary-currency: Currency ticker to look up on bitaverage (default: `USD`)
* --summary-currency-prefix: Prefix when printing currency (default: `USD $`)

## Example Usage

Unfortunately the python plugin framework doesn't pretty-print, nor does
lightning-cli, and json_pp doesn't maintain order, so I use a hacky 'tr':

```
$ lightning-cli summary | tr ',' '\n'
{"network": "TESTNET"
 "my_address": "031a3478d481b92e3c28810228252898c5f0d82fc4d07f5210c4f34d4aba56b769@165.227.30.200"
 "num_utxos": 5
 "utxo_amount": "1.20119332000btc = USD $4589.24"
 "num_channels": 31
 "num_connected": 1
 "num_gossipers": 32
 "avail_out": "0.27095103btc = USD $1035.19"
 "avail_in": "2.06940379btc = USD $7906.30"
 "channels": ["         ---------------------------/          :02ac05912f89e43b88de3472e8c3003b"
 "          -------------------------/-          :02dd4cef0192611bc34cd1c3a0a7eb0f"
 "         /---------------------------          :02a13878947a133d7c96e70303a9bf27 (priv)"
 "                      /-                       :033e2db012833d997e3c"
 "                      /--                      :Kenny_Loggins"
 "/--------------------------------------------- :DeutscheTestnetBank"
 "/--------------------------------------------- :BlueLagoon1"
 "/--------------------------------------------- :0270dd38e8af9a64b4a483ab12b6aeb1"
 "                      /--                      :btctest.lnetwork.tokyo"
 "                    /-----                     :microbet.fun"
 "/--------------------------------------------- :02fcab6e34a2ad21be2a752ab96d13f5 (priv)"
 "/--------------------------------------------- :htlc.me"
 "                   /--------                   :02229ea9a7a4f9bf8bf25ce225079aed"
 "/--------------------------------------------- :025d5b572a94235cfcbdc429181b2b88"
 "          /-------------------------           :03c56de3a84336b4a939777ace9ecbef (priv)"
 "              /------------------              :LiteStrikeBTClnd"
 "      /----------------------------------      :037c9cf1cde4414c59407d547b7eac08 (priv)"
 "                       /                       :03490a74e4def9125a84aee2d84e8cfe"
 "  ---------------------/---------------------  :aranguren.org"
 "                       /                       :03cc6603e1f6df535dd8b423284f2c09 (priv)"
 "                      /-                       :cyclopes"
 "/--------------------------------------------- :02b73a2160863e925e9fa978b0ddc56b (priv)"
 "                   /--------                   :lnd-testnet.ignios.net"
 "                    /-----                     :0327a104108173d4a4f34ab2cbc3084c (priv)"
 "                     /----                     :dwarf"
 "                      /-                       :028133777757ce281658804dd82f5758 (priv)"
 "          /-------------------------           :02db62ffff5c35be74e7f856bba136db (priv)"
 "                       /                       :Lightning Tea"
 "                      /--                      :03015ac044f5fa9768ededf6fed9c0ff (priv)"
 "                      /--                      :LND-Neutrino-TEST"
 "/--------------------------------------------- :0270685ca81a8e4d4d01"]}
```
