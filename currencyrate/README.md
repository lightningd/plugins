# Currencyrate plugin

This plugin provides Bitcoin currency conversion functions using various
different backends and taking the median. It caches results for an hour.

## Installation

For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)

## Options:

* --add-source: Add a source, of form NAME,URL,MEMBERS where URL and MEMBERS
  can have `{currency}` and `{currency_lc}` to substitute for upper-case and
  lower-case currency names.  MEMBERS is how to deconstruct the result, for
  example if the result is `{"USD": {"last_trade": 12456.79}}` then MEMBERS
  would be "USD,last_trade".
* --disable-source: Disable the source with this name.

You can specify these options multiple times to add or disable multiple sources.

## Commands

`currencyrates` returns the number of msats per unit from every backend, eg:

```
$ lightning-cli currencyrates USD
{
   "coindesk": "5347227msat",
   "bitstamp": "5577515msat",
   "coingecko": "5579273msat",
}
```

`currencyconvert` converts the given amount and currency into msats, using the
median from the above results. eg:

```
$ lightning-cli currencyconvert 100 USD
{
   "msat": "515941800msat"
}
```

## Default Currency Sources

Thanks to those services who provide this information.  Coindesk require
a blurb, so I did that for everyone (quoting from their front page):

* www.bitstamp.net: "The original global crypto exchange."
* api.coingecko.com: "The world's most comprehensive cryptocurrency API"
* api.coindesk.com: "Powered by CoinDesk: https://www.coindesk.com/price/bitcoin"
* api.coinbase.com: "The easiest place to buy, sell, and manage your cryptocurrency portfolio."
* blockchain.info: "The World's Most Popular Way to Buy, Hold, and Use Crypto"
