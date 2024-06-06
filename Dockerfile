ARG CLN_VERSION="24.02.2"

FROM elementsproject/lightningd:v${CLN_VERSION}

ARG EXTRA_PLUGINS='--recurse-submodules=csvexportpays \
--recurse-submodules=graphql \
--recurse-submodules=jwt-factory \
--recurse-submodules=python-teos \
--recurse-submodules=trustedcoin \
--recurse-submodules=webhook'

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-wheel \
    python3-dev \
    python3-venv \
    libleveldb-dev \
    pkg-config \
    libc-bin \
    git \
    libpq-dev \
    postgresql \
    curl && \
    python3 -m pip install --upgrade pip

COPY . /tmp/plugins
RUN mkdir /tmp/oldplugins && mv /usr/local/libexec/c-lightning/plugins/* /tmp/oldplugins/ && \
    cd /usr/local/libexec/c-lightning/plugins && \
    git clone --depth 1 --shallow-submodules -j4 \
        ${EXTRA_PLUGINS} \
        file:///tmp/plugins . && \
    pip3 install setuptools && \
    find -name requirements.txt -print0 | xargs -0 -n 1 pip3 install -r && \
    mv /tmp/oldplugins/* /usr/local/libexec/c-lightning/plugins && rmdir /tmp/oldplugins

EXPOSE 9735 9835
ENTRYPOINT  [ "/usr/bin/tini", "-g", "--", "./entrypoint.sh" ]
