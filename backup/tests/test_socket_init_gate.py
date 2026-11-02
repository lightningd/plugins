"""Socket backup initialization must preserve an already populated remote.

The existing FileBackend(create=True) protects a local destination; the socket
backend must enforce the corresponding metadata gate for backup-cli init.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backends import get_backend
from socketbackend import SocketBackend


@pytest.mark.parametrize(
    "remote_state,creating,accepted",
    [
        ((0, 0, 0), True, True),     # empty remote: valid new backup
        ((10, 9, 10), True, False), # active history: protected
        ((0, 0, 1), True, False),   # rewound to zero: still has history
        ((10, 9, 10), False, True), # reopen existing remote: valid
    ],
)
def test_socket_backend_create_gate(monkeypatch, remote_state, creating, accepted):
    # Use the actual get_backend -> SocketBackend.initialize flow. The
    # transport returns a deterministic server metadata frame.
    monkeypatch.setattr(SocketBackend, "connect", lambda self: None)

    def metadata(self):
        self.protocol = 1
        self.version, self.prev_version, self.version_count = remote_state

    monkeypatch.setattr(SocketBackend, "_request_metadata", metadata)

    url = "socket:127.0.0.1:10001"
    if accepted:
        backend = get_backend(url, create=creating)
        assert (
            backend.version,
            backend.prev_version,
            backend.version_count,
        ) == remote_state
    else:
        with pytest.raises(ValueError, match="remote backup already contains changes"):
            get_backend(url, create=creating)
