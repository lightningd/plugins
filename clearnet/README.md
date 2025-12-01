# clearnet enforcer plugin
This plugin aims to prefer usage over clearnet connections.
It does so by disconnecing TOR connections when there are known and usable
clearnet addresses.

# Installation

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) to run this
plugin like a binary. After `uv` is installed you can simply run

```
lightning-cli plugin start /path/to/clearnet.py
```

For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)

# Options

# Methods
## clearnet-enforce [peer_id]
Tries to enforce clearnet on all peer or on a given peer_id
