FROM elementsproject/lightningd

ARG EXTRA_PLUGINS='--recurse-submodules=csvexportpays \
--recurse-submodules=graphql \
--recurse-submodules=jwt-factory \
--recurse-submodules=python-teos \
--recurse-submodules=trustedcoin \
--recurse-submodules=webhook'

RUN apt-get update && apt-get install -y --no-install-recommends build-essential python3-wheel python3-dev python3-venv libleveldb-dev pkg-config libc-bin git libpq-dev postgresql

COPY . /tmp/plugins
RUN mkdir /tmp/oldplugins && mv /opt/lightningd/plugins/* /tmp/oldplugins/ && \
    cd /opt/lightningd/plugins && \
    git clone --depth 1 --shallow-submodules -j4 \
        ${EXTRA_PLUGINS} \
        file:///tmp/plugins . && \
    pip3 install setuptools && \
    find -name requirements.txt -exec pip3 install -r {} \; && \
    mv /tmp/oldplugins/* /opt/lightningd/plugins/ && rmdir /tmp/oldplugins

EXPOSE 9735 9835
ENTRYPOINT  [ "/usr/bin/tini", "-g", "--", "./entrypoint.sh" ]
