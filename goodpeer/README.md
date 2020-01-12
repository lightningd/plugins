# Goodpeer

Find sufficiently connected low-fees peers.

## Usage
```
lightning-cli goodpeers
```
Will return a reversely-sorted list of peers (the better the lower).

## Improvements

The algo is very basic as it only computes the median base and ppm fees of all
channels of a node, the lower their sum, the better the score.

- Be smarter and include us to sort peers: i.e. how many new viable channels
would open a channel funding with this peer ?
- Include a bias toward small or big payments (add a bigger ratio to either
base_fee or fee_ppm in the scoring, respectively).
- Add a new command taking a peer id as parameter and which returns stats about
a potential channel funding with this peer.

## Installation

If you have [reckless](https://github.com/darosior/reckless) installed, you can
install it just with:
```
lightning-cli install_plugin goodpeer
```

Otherwise, all usual methods: `lightning-cli plugin start goodpeer.py`, `--plugin
goodpeer.py` startup option, or putting it in `~/.lightning/bitcoin/plugins/`.
