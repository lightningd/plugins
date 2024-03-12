# Balanced AMP Payments

This plugin computes an optimal split of a payment amount for the use of AMP.
The split is optimal in the sense that it reduces the imbalance of the funds of the node.

More theory about imbalances and the algorithm to decrease the imblance of a node was
suggested by [this research paper](https://arxiv.org/abs/1912.09555) by Rene Pickhardt and Mariusz Nowostawski: 

This software is an adopted version as [discussed in this post on the lightning-dev](https://lists.linuxfoundation.org/pipermail/lightning-dev/2020-January/002418.html) mailing
lis and was suggested to be created by ZmnSCPxj.

> :warning: This plugin is still work in progress and may not work in all edge cases. :construction:

## Command line options

The plugin exposes no new command line options.
   
## JSON-RPC methods

The plugin also exposes the following methods:

 - `amp_invoice_amounts`: splits an amount that is supposed to be received into smaller amounts in a way that maximally reduces the imbalance of the node's channels.

 - `amp_pay_amounts`: splits an amount that is supposed to be sent into smaller amounts in a way that maximally decreases the imbalance of the node's channels.

Both API calls return a dictionary with short channel IDs and amounts
   
## Support: 
If you like my work consider a donation at https://patreon.com/renepickhardt or https://tallyco.in/s/lnbook


[lib]: https://github.com/ElementsProject/lightning/pull/1888
