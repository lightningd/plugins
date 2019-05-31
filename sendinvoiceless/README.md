# Invoiceless payment plugin

This plugin sends some msatoshis without needing to have an invoice from the
receiving node. It uses circular payment: takes the money to the receiving node,
pays in the form of routing fee, and brings some change back to close the circle.


## Installation

For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)


## Usage
Once the plugin is active you can send payment by running:

```
lightning-cli sendinvoiceless nodeid msatoshi [maxfeepercent] [retry_for] [exemptfee]
```

If you want to skip/default certain optional parameters but use others, you can
use always the `lightning-cli -k` (key=value) syntax like this:

```bash
lightning-cli sendinvoiceless -k nodeid=022368... msatoshi=1000 retry_for=600
```

### Parameters

- The `nodeid` is the identifier of the receiving node.
- The `msatoshi` parameter defines the millisatoshi amount to send.
  Can be denominated in other units, i.e.: `1000000sat`, `0.01btc` or `10mbtc`.
- The `maxfeepercent` limits the money paid in fees and defaults to 0.5.
  The `maxfeepercent` is a percentage of the amount that is to be paid.
- The `exemptfee` option can be used for tiny payments which would be dominated
  by the fee leveraged by forwarding nodes. Setting exemptfee allows the
  maxfeepercent check to be skipped on fees that are smaller than exemptfee
  (default: 5000 millisatoshi).

The command will keep finding routes and retrying the payment until it succeeds,
or the given `retry_for` seconds pass. retry_for defaults to 60 seconds and can
only be an integer.

### See also
For a detailed explanation of the optional parameters, see also the manpage
of the `pay` plugin: `lightning-pay(7)`


## List payments
If you want to check if you got paid by using this method, you can call this:

```
lightning-cli receivedinvoiceless [min_amount]
```

This will return an array of detected payments using this method. The plugin
will filter the results by the optional `min_amount` parameter (default: 10sat).
This will suppress unexpected results caused by route fee fuzzing and changed
past channel fees. The results will contain the `amount_msat` and `timestamp`
of the payments.

NOTE: The plugin currently does not use a database, so it can only assume fees
have not changed in the past. It will also apply default fees for already
forgotten channels. In both cases result can be slightly off by the changed fee.


## Weaknesses
This is kind of hack with some downsides:
- The route is twice as long because of the circular payment. This will increase fees and failure probability.
- The payee receives the money as a routing fee: hard to associate with anything, distinguish from the usual fees.
- If the payment is going on a circular route A-B-C-D-A to pay C, and the same malicious entity controls B and D, the money can be stolen by skipping C.
