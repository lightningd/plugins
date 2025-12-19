# Prometheus plugin for c-lightning

This plugin exposes some key metrics from c-lightning in the prometheus format
so it can be scraped, plotted and alerts can be created on it. The plugin adds
the following command line arguments:

 - `prometheus-listen`: the IP address and port to bind the HTTP server to
   (default: `127.0.0.1:9750`)

Exposed variables include:

 - `node`: ID, version, ...
 - `peers`: whether they are connected, and how many channels are currently
   open
 - `channels`: fund allocations, spendable funds, and how many unresolved
   HTLCs are currently attached to the channel
 - `funds`: satoshis in on-chain outputs, satoshis allocated to channels and
   total sum (may be inaccurate during channel resolution).

## Installation
You need [uv](https://docs.astral.sh/uv/getting-started/installation/) to run this
plugin like a binary. After `uv` is installed you can simply run

```
lightning-cli plugin start /path/to/prometheus.py
```

If you use `systemd` to start CLN, you must have `uv` in the `PATH` that `systemd` uses, which is likely different than the `PATH` from your shell. Most `uv` installation methods install `uv` into your user's home directory (`~/.local/bin` or `~/.cargo/bin`), which `systemd` cannot access.

You can either:

**Option 1: Install `uv` system-wide** (recommended):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR="/usr/local/bin" sh
```

**Option 2: Copy your existing user installation**:
```bash
sudo cp "$(command -v uv)" /usr/local/bin/uv
```

**Option 3: Configure your systemd service** to use a custom `PATH` (see systemd documentation).

To verify `uv` is accessible to systemd:
```bash
sudo systemd-run --user --wait command -v uv
```
This should output `/usr/local/bin/uv`.

For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)
