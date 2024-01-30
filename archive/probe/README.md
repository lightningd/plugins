# Network Probe plugin

This plugin regularly performs a random probe of the network by sending a
payment to a random node in the network, with a random `payment_hash`, and
observing how the network reacts. The random `payment_hash` results in the
payments being rejected at the destination, so no funds are actually
transferred. The error messages however allow us to gather some information
about the success probability of a payment, and the stability of the channels.

The random selection of destination nodes is a worst case scenario, since it's
likely that most of the nodes in the network are leaf nodes that are not
well-connected and often offline at any point in time. Expect to see a lot of
errors about being unable to route these payments as a result of this.

The probe data is stored in a sqlite3 database for later inspection and to be
able to eventually draw pretty plots about how the network stability changes
over time. For now you can inspect the results using the `sqlite3` command
line utility:

```bash
sqlite3  ~/.lightning/probes.db "select destination, erring_channel, failcode from probes"
```

Failcode -1 and 16399 are special:

 - -1 indicates that we were unable to find a route to the destination. This
    usually indicates that this is a leaf node that is currently offline.

 - 16399 is the code for unknown payment details and indicates a successful
   probe. The destination received the incoming payment but could not find a
   matching `payment_key`, which is expected since we generated the
   `payment_hash` at random :-)
