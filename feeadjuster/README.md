# Fee Adjuster

This plugin dynamically adjusts fees according to channel balances. The default behaviour is to automatically adjust fees at startup
and following forwarding events. There is a threshold for balance deltas that must be crossed before an update is triggered.  It can
also set the max htlc for channels according to available liquidity. This may reduce transaction failures but it will also reveal
information about what the current channel balance is.

## Options

- `feeadjuster-deactivate-fuzz` boolean (default `False`) deactivates update threshold randomization and hysterisis
- `feeadjuster-deactivate-fee-update` boolean (default `False`) deactivates automatic fee updates for forward events
- `feeadjuster-threshold` default 0.05 - Relative channel balance delta at which to trigger an update. Default 0.05 means 5%. Note: it's also fuzzed by 1.5%.
- `feeadjuster-threshold-abs` default 0.001btc - Absolute channel balance delta at which to always trigger an update. Note: it's also fuzzed by 1.5%.
- `feeadjuster-enough-liquidity` default 0msat (turned off) - Beyond this liquidity do not adjust fees. 
This also modifies the fee curve to achieve having this amount of liquidity.
- `feeadjuster-adjustment-method` Adjustment method to calculate channel fee. Can be 'default', 'soft' for less difference or 'hard' for higher difference.
- `feeadjuster-imbalance` default 0.5 (always acts) - Ratio at which channel imbalance the feeadjuster should start acting. Set higher or lower values to 
limit feeadjuster's activity to more imbalanced channels. E.g. 0.3 for '70/30'% or 0.6 for '40/60'%.
- `feeadjuster-feestrategy` Sets the per channel fee selection strategy. Can be 'global' (default) to use global config or default values, or 'median' to use 
the median fees from peers of peer.
- `feeadjuster-median-multiplier` Sets the factor with which the median fee is multiplied if using the fee strategy
'median'. This allows over- or underbidding other nodes by a constant factor (default: 1.0).
- `feeadjuster-max-htlc-steps` Default 0 (turned off). Sets the number of max htlc adjustment steps. If our local channel balance drops below a step level
it will reduce the max htlc to that level, which can reduce local routing channel failures.  A value of 0 disables the stepping.
- `feeadjuster-basefee` Default False, Also adjust base fee dynamically. Currently only affects median strategy.
