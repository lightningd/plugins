# Balance Sharin Plugin

This is Work in Progress by Michael Ziegler and Rene Pickhadt from NTNU to extend the Lightning Network Protocol with the ability of nodes sharing their balance information with neighbors. This is needed to provide JIT-Routing functionality. Read more on: https://wiki.fulmo.org/wiki/Challenges_May_2020#JIT_Routing_.2F_Sharing_balance_information

## Installation


in order to use the plugin your lightnig node needs to be compild with devolper commands activated.
You can build c-lightning with `DEVELOPER=1` to use dev commands listed in `cli/lightning-cli help`.
./configure --enable-developer will do that.

According to BOLT 01 lightning messages use TLV encoding (Type, Length, Value). Types are reflecting semantics. Gossip messages have typ 256 until 512.

We will create our first qurery message with typ `347` which is odd and the checksum is `14` which we see practical as we target to create BOLT 14. 

we use `lightning/devtools/decodemsg` to decode messages also we use `lightning-cli dev-sendcustommsg node_id msg` to send custom messages (starting with type 347) and we use the plugin `custommsg` hook to decode custommessages which are not known to the lightning node


## For developers
To test this plugin you need to have at least two lightning nodes running. It is easiest if both nodes are complied with `DEVELOPER=1` and have the plugin activated.
We make use of the autoreload plugin as you don't have to restart your lightning node everytime you make changes to your plugin code.

note that if you use the autoreload plugin you MUST pass the path the the balancesharing plugin as a command line argument to lightningd instead of writing it in the config file. e.g:

```
lightningd --network regtest --autoreload-plugin=/path/to/plugins/balancesharing/balancesharing.py
```


For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)

## Example Usage

tba

