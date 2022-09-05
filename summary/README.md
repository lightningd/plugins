# Summary plugin

This plugin is a little hack to show a summary of your node, including
fiat amounts.  If you have pylightning 0.0.7.1 or above, you get nice linegraphs,
otherwise normal ASCII.

## Installation

For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)

## Options:

* --summary-currency: Currency ticker to look up on bitaverage (default: `USD`)
* --summary-currency-prefix: Prefix when printing currency (default: `USD $`)

## Example Usage

Unfortunately the python plugin framework doesn't pretty-print, nor does
lightning-cli, so best viewed with -H:

```
$ lightning-cli -H summary
network=TESTNET
my_address=031a3478d481b92e3c28810228252898c5f0d82fc4d07f5210c4f34d4aba56b769@165.227.30.200
num_utxos=5
utxo_amount=1.20119332000btc (USD $4473.84)
num_channels=29
num_connected=2
num_gossipers=1
avail_out=0.27095103btc (USD $1009.16)
avail_in=2.05851379btc (USD $7666.93)
fees_collected=0.00000012341btc (USD $0.00)
channels_key=P=private O=offline
channels=          ├────────────╢                       (O):02ac05912f89e43b88de3472e8c3003b
           ├───────────╢                       (O):02dd4cef0192611bc34cd1c3a0a7eb0f
                       ╟────────────┤          (PO):02a13878947a133d7c96e70303a9bf27
                       ║                       (O):033e2db012833d997e3c
                       ╟┤                      (O):Kenny_Loggins
                       ╟──────────────────────┤(O):DeutscheTestnetBank
                       ╟─────────────────────┤ (O):BlueLagoon1
                       ╟──────────────────────┤(O):0270dd38e8af9a64b4a483ab12b6aeb1
                       ╟┤                      (O):btctest.lnetwork.tokyo
                       ╟─┤                     (O):microbet.fun
                       ╟──────────────────────┤(PO):02fcab6e34a2ad21be2a752ab96d13f5
                       ╟──────────────────────┤(O):htlc.me
                       ╟───┤                   (O):02229ea9a7a4f9bf8bf25ce225079aed
                       ╟─────────────────────┤ (O):025d5b572a94235cfcbdc429181b2b88
                       ╟────────────┤          (PO):03c56de3a84336b4a939777ace9ecbef
                       ╟────────┤              (O):LiteStrikeBTClnd
                       ╟────────────────┤      (PO):037c9cf1cde4414c59407d547b7eac08
                       ║                       (O):03490a74e4def9125a84aee2d84e8cfe
             ├─────────┼─────────┤             (O):aranguren.org
                       ║                       (PO):03cc6603e1f6df535dd8b423284f2c09
                       ║                       (O):cyclopes
                       ╟─────────────────────┤ (PO):02b73a2160863e925e9fa978b0ddc56b
                       ╟───┤                   (O):lnd-testnet.ignios.net
                       ╟─┤                     (PO):0327a104108173d4a4f34ab2cbc3084c
                       ╟─┤                     :dwarf
                       ║                       (PO):028133777757ce281658804dd82f5758
                       ╟────────────┤          (PO):02db62ffff5c35be74e7f856bba136db
                       ╟┤                      (PO):03015ac044f5fa9768ededf6fed9c0ff
                       ╟──────────────────────┤:0270685ca81a8e4d4d01
