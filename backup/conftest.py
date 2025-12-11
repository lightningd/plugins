import pytest
import os
import subprocess
import time
import socket
import asyncio
import threading

from pyln.testing.fixtures import *  # noqa: F403
from asysocks.server import SOCKSServer

cli_path = os.path.join(os.path.dirname(__file__), "backup-cli")


def wait_for_port(host, port, timeout=5.0):
    """Poll until a TCP port starts accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.connect((host, port))
                return
            except (ConnectionRefusedError, OSError):
                time.sleep(0.05)
    raise RuntimeError(f"Backup server did not start listening on {host}:{port}")


@pytest.fixture
def running_backup_server(node_factory, directory):
    """
    Spins up a local backup server on a random port for testing.
    Yields (host, port).
    """

    file_url = "file://" + os.path.join(directory, "backup.dbak")

    subprocess.check_call([cli_path, "init", file_url])

    host = "127.0.0.1"
    port = node_factory.get_unused_port()

    # Start server
    server_proc = subprocess.Popen(
        [cli_path, "server", file_url, f"{host}:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Wait until server is actually listening
        wait_for_port(host, port, timeout=5)
        yield host, port
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            server_proc.kill()


@pytest.fixture
def socks5_proxy(node_factory):
    """
    Spins up a local SOCKS5 proxy server on a random port for testing.
    Yields (host, port) as a plain tuple.
    """
    host = "127.0.0.1"
    port = node_factory.get_unused_port()

    server = SOCKSServer(host, port)

    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.run())
        finally:
            loop.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    wait_for_port(host, port)

    yield host, port
