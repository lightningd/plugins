"""Create a backend instance based on URI scheme dispatch."""

from typing import Type
from urllib.parse import urlparse

from backend import Backend
from socketbackend import SocketBackend
from filebackend import FileBackend


def resolve_backend_class(backend_url):
    backend_map: Mapping[str, Type[Backend]] = {
        "file": FileBackend,
        "socket": SocketBackend,
    }
    p = urlparse(backend_url)
    backend_cl = backend_map.get(p.scheme, None)
    return backend_cl


def get_backend(destination, create=False, require_init=False):
    backend_cl = resolve_backend_class(destination)
    if backend_cl is None:
        raise ValueError(
            "No backend implementation found for {destination}".format(
                destination=destination,
            )
        )
    backend = backend_cl(destination, create=create)
    initialized = backend.initialize()
    if require_init and not initialized:
        kill(
            "Could not initialize the backup {}, please use 'backup-cli' to initialize the backup first.".format(
                destination
            )
        )
    assert backend.version is not None
    assert backend.prev_version is not None
    return backend
