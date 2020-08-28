#!/bin/bash -x
set -e

CWD=$(pwd)
export SLOW_MACHINE=1
export PATH="$HOME/.local/bin:$(pwd)/dependencies/bin:$PATH"
export PYTEST_PAR=10
export TEST_DEBUG=1
export LIGHTNING_VERSION=${LIGHTNING_VERSION:-master}
export PYTHONPATH=/tmp/lightning/contrib/pyln-client:/tmp/lightning/contrib/pyln-testing:/tmp/lightning/contrib/pylightning:$$PYTHONPATH
export BITCOIND_VERSION="0.20.1"

mkdir -p dependencies/bin

# Download bitcoind and bitcoin-cli 
echo 'travis_fold:start:script.0'
if [ ! -f dependencies/bin/bitcoind ]; then
    wget https://storage.googleapis.com/c-lightning-tests/bitcoin-${BITCOIND_VERSION}-x86_64-linux-gnu.tar.bz2
    tar -xjf bitcoin-${BITCOIND_VERSION}-x86_64-linux-gnu.tar.bz2
    mv bitcoin-${BITCOIND_VERSION}/bin/* dependencies/bin
    rm -rf bitcoin-${BITCOIND_VERSION}-x86_64-linux-gnu.tar.gz bitcoin-${BITCOIND_VERSION}
fi
echo 'travis_fold:end:script.0'

echo 'travis_fold:start:script.1'
pyenv global 3.7
pip3 install --quiet --upgrade pip
pip3 install --user --quiet \
     mako==1.0.14 \
     psycopg2-binary>=2.8.3 \
     pytest-timeout==1.3.3 \
     pytest-xdist==1.30.0 \
     pytest-cover \
     coverage \
     codecov \
     mrkd==0.1.6

echo 'travis_fold:end:script.1'

# Install the pyln-client and testing library matching c-lightning `master`

PY3=$(which python3)

echo 'travis_fold:start:script.2'
git clone --recursive https://github.com/ElementsProject/lightning.git /tmp/lightning
(
    cd /tmp/lightning
    git checkout "$LIGHTNING_VERSION"
    ./configure --disable-valgrind
    make -j 16 > /dev/null
)
echo 'travis_fold:end:script.2'

# Collect libraries that the plugins need and install them
echo 'travis_fold:start:script.3'
find . -name requirements.txt -exec pip3 install --quiet --upgrade --user -r {} \;

# Force the tests to use the latest and greatest version of pyln
pip install -U pyln-testing>=0.8.2 pyln-client>=0.8.2
echo 'travis_fold:end:script.3'

# Add the directory we put the newly compiled lightningd in
export PATH="/tmp/lightning/lightningd/:$PATH"

# Force coverage to write files in $CWD
export COVERAGE_FILE="$CWD/.coverage"
export COVERAGE_RCFILE="$CWD/.coveragerc"

export PYTHONPATH="$CWD"
pytest -vvv --timeout=550 --timeout_method=thread -p no:logging -n 5 --cov

codecov --env COMPAT,DEVELOPER,EXPERIMENTAL_FEATURES
