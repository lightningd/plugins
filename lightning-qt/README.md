# lightning-qt
*bitcoin-qt for C-Lightning, as simple as : `lightning-cli gui`*
![lightning-qt screenshot](screenshot.png)


## Install

The easiest way is to install it with [reckless](https://github.com/darosior/reckless). If you
have `lightningd` running with [the reckless plugin](https://github.com/darosior/reckless) loaded you
can install `lightning-qt` with:
```
lightning-cli install_plugin lightning-qt
```

Otherwise the traditional solution:
```
git clone https://github.com/lightningd/plugins && cd plugins/lightning-qt
make
lightningd --plugin=lightning-qt.py
```

You can also add `lightning-qt` directly in the default `plugins` directory for it to be
automatically loaded at startup:
```
git clone https://github.com/lightningd/plugins
cp -r plugins/lightning-qt ~/.lightning/plugins/lightning-qt
make
lightningd
```

Or you can even start it dynamically like (C-lightning v0.7.2 and above):
```
git clone https://github.com/lightningd/plugins && cd plugins/lightning-qt
make
lightning-cli plugin start lightning-qt.py
```


## Usage

Just with `lightning-cli gui`!

You can also use lightning-qt in standalone mode. It will connect to a socket which path can be
given as a command line option (and defaults to $HOME/.lightning/lightning-rpc) : this can be
useful to use lightning-qt as a remote control for your lightning node hosted on another computer,
you could for example share a socket through ssh and start lightning-qt listening on this socket ie:
```bash
python3 lightning-qt --socket-path /path/to/unixdomain/socket
```


## Contributing

We use [forms](forms/)(ui files) to design pages: these are handled by PyQt5 with the `pyuic5`
command line tool (installed with `pip install PyQt5`). If you modify a ui file (you may want to
use [QDesigner](https://doc.qt.io/qt-5/qtdesigner-manual.html)), you can regenerate the Python code like:
```
pyuic5 forms/channelspage.ui -o forms/ui_channelsPage.py
```

Please also note that PyQt5 has *__a very bad__* way to handle exception in slots: in short you cannot
`except` a raised exception in a [slot](https://doc.qt.io/qt-5/signalsandslots.html).

### Icons

If you contribute an icon, please do add its source and license information to the [icons
README](res/icons/README.md).
