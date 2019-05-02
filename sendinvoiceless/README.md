# Invoiceless payment plugin

This plugin sends some msatoshis without needing to have an invoice from the receiving node. It uses circular
payment: takes the money to the receiving node, pays in the form of routing fee, and brings some change back to
close the circle.

The plugin can be started with `lightningd` by adding the following `--plugin` option
(adjusting the path to wherever the plugins are actually stored):

```
lightningd --plugin=/path/to/plugin/sendinvoiceless.py
```

Once the plugin is active you can send payment by running:
`lightning-cli sendinvoiceless nodeid msatoshi [maxfeepercent] [retry_for] [exemptfee]`

The `nodeid` is the identifier of the receiving node. The `maxfeepercent` limits the money paid in fees and
defaults to 0.5. The maxfeepercent' is a percentage of the amount that is to be paid. The `exemptfee` option can
be used for tiny payments which would be dominated by the fee leveraged by forwarding nodes. Setting exemptfee
allows the maxfeepercent check to be skipped on fees that are smaller than exemptfee (default: 5000 millisatoshi).

The command will keep finding routes and retrying the payment until it succeeds, or the given `retry_for` seconds
pass. retry_for defaults to 60 seconds and can only be an integer.

## Known weaknesses
This is kind of hack with some downsides:
- The route is twice as long because of the circular payment. This may increase fees and failure probability.
- The payee receives the money as a routing fee: hard to associate with anything, distinguish from the usual fees.
- If the payment is going on a circular route A-B-C-D-A to pay C, and the same malicious entity controls B and D, the money can be stolen by skipping C.
