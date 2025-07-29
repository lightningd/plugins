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
### Using uv (recommended)
* Install `uv` and make the plugin executable
```
pip install --upgrade pip uv
chmod a+x prometheus.py
```
Then you can add _just that file_ to your Core Lightning plugins directory. The plugin should start automatically and its dependencies will be installed on-the-fly when the node comes up.

### Using poetry (legacy)
If you don't want to use `uv`, you can still use `poetry`. You need to update the shebang line to point the OS at the correct interpreter (`python3`) though:
```
sed -i 's#-S uv run --script#python3#' prometheus.py
```

Then install `poetry` and build the package:
```
pip install --upgrade pip poetry
poetry install --only main
```

This is an example snippet for installing the plugin's dependencies and cleaning up afterwards:
```
PLUGIN_PATH=/opt/plugins
RAW_GH_PLUGINS=https://raw.githubusercontent.com/lightningd/plugins/master
mkdir -p ${PLUGIN_PATH}

pip3 install --break-system-packages --upgrade pip wheel poetry

# Add custom plugins (prometheus)
## This replaces the shebang line that by default uses uv for package management
(cd $PLUGIN_PATH; wget -q $RAW_GH_PLUGINS/prometheus/README.md \
  && wget -q $RAW_GH_PLUGINS/prometheus/pyproject.toml \
  && wget -q $RAW_GH_PLUGINS/prometheus/poetry.lock \
  && wget -q $RAW_GH_PLUGINS/prometheus/prometheus.py \
  && sed -i 's#-S uv run --script#python3#' prometheus.py \
  && poetry config virtualenvs.create false \
  && PIP_BREAK_SYSTEM_PACKAGES=1 poetry install --only main \
  && rm -f README.md pyproject.toml poetry.lock)

chmod a+x $PLUGIN_PATH/*
```
