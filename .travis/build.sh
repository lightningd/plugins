#!/bin/bash -x
set -e

CWD=$(pwd)
export SLOW_MACHINE=1
export PATH=$CWD/dependencies/bin:$CWD/dependencies/usr/local/bin/:/tmp/lightning/lightningd/:"$HOME"/.local/bin:"$PATH"
export PYTEST_PAR=10
export TEST_DEBUG=1
export LIGHTNING_VERSION=${LIGHTNING_VERSION:-master}
export PYTHONPATH=/tmp/lightning/contrib/pyln-client:/tmp/lightning/contrib/pyln-testing:/tmp/lightning/contrib/pylightning:$$PYTHONPATH

mkdir -p dependencies/bin

# Download bitcoind and bitcoin-cli 
if [ ! -f dependencies/bin/bitcoind ]; then
    wget https://bitcoin.org/bin/bitcoin-core-0.17.1/bitcoin-0.17.1-x86_64-linux-gnu.tar.gz
    tar -xzf bitcoin-0.17.1-x86_64-linux-gnu.tar.gz
    mv bitcoin-0.17.1/bin/* dependencies/bin
    rm -rf bitcoin-0.17.1-x86_64-linux-gnu.tar.gz bitcoin-0.17.1
fi

pyenv global 3.7
pip3 install --upgrade pip
pip3 install --user --quiet \
     pyln-testing \
     mako==1.0.14 \
     psycopg2-binary==2.8.3 \
     pytest-timeout==1.3.3 \
     pytest-xdist==1.30.0

# Install the pyln-client and testing library matching c-lightning `master`

PY3=$(which python3)

git clone --recursive https://github.com/ElementsProject/lightning.git /tmp/lightning
(cd /tmp/lightning && git checkout "$LIGHTNING_VERSION")
(cd /tmp/lightning/contrib/pyln-client && $PY3 setup.py install)
(cd /tmp/lightning/contrib/pyln-testing && $PY3 setup.py install)

# Compiling lightningd can be noisy and time-consuming, cache the binaries
if [ ! -f "$CWD/dependencies/usr/local/bin/lightningd" ]; then
    (
	cd /tmp/lightning && \
	./configure --disable-valgrind && \
	make -j 8 DESTDIR=dependencies/
    )
fi

# Collect libraries that the plugins need and install them
find . -name requirements.txt -exec pip3 install --user -r {} \;

pytest -vvv --timeout=550 --timeout_method=thread -p no:logging -n 10
