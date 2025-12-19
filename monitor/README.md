# Monitor plugin

Monitors the health of your peers and helps you to decide if you might want to close a channel

## Installation

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) to run this
plugin like a binary. After `uv` is installed you can simply run

```
lightning-cli plugin start /path/to/monitor.py
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

## Example Usage

Unfortunately the python plugin framework doesn't pretty-print, nor does
lightning-cli, so best viewed with -H (sorry for all the slasshes in the output. nothing I can do about it at this point):

```
lightning-cli -H monitor

{
    \"num_connected\": 26,
    \"num_channels\": 37,
    \"states\": [
        \"CHANNELD_NORMAL: 37\"
    ],
    \"channels\": {
        \"CHANNELD_NORMAL\": [
            \"024a8228d764091fce2ed67e1a7404f83e38ea3c7cb42030a2789e73cf3b341365\	connected\	their fees\	xx.xx% owned by us\	537914x2372x0\",
            \"032e04b67641c00444af1d83145c0b63bac8316a6afb8fec0f87938295ed8bb129\	disconnected\	their fees\	xx.xx% owned by us\	539125x1288x0\",
            \"0279c22ed7a068d10dc1a38ae66d2d6461e269226c60258c021b1ddcdfe4b00bc4\	connected\	our fees\	xx.xx% owned by us\	539467x852x0\",
 	    ...
            \"0227d5b940cba21be92244953475ccdd3cefbed8f397be03e3155a5f41f304fc93\	connected\	their fees\	xx.xx% owned by us\	581418x2157x0\"
        ]
    }
}
```

As you can see you will see a list of channels to which you are connected or disconnected. How much percent of the funds is owned by you and who has to pay the fees in case of force channel closing.


Or if you just want to see the channels which are currently disconnected from peers

```
lightning-cli -H monitor | grep "disconnected"
```

