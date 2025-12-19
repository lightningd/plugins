# Installation

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) to run this
plugin like a binary. After `uv` is installed you can simply run

```
lightning-cli plugin start /path/to/persistent-channels.py
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

# Persistent Channels plugin

`lightningd` automatically tracks channels internally and will make
sure to reconnect to a peer if it has a channel open with it. However,
it only tracks the channel itself, it does not re-open a channel that
was closed.

The persistent channels plugin allows you to describe a number of
channels you'd like to have open at any time and the plugin will
attempt to maintain that state. The plugin keeps a list of desired
channels that should be opened and operational and will check every 30
seconds if it needs to open a new channel, or re-open a channel that
is currently being closed.
