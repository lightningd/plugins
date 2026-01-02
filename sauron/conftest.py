import socket
import pytest

# Store original getaddrinfo
_original_getaddrinfo = socket.getaddrinfo


def getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    """Force IPv4 only by filtering out IPv6 addresses"""
    results = _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    if results:
        ip = results[0][4][0]
        print(f"Connecting to {host} via IPv4: {ip}")
    return results


@pytest.fixture(scope="session", autouse=True)
def force_ipv4():
    """Force all network connections to use IPv4"""
    socket.getaddrinfo = getaddrinfo_ipv4_only
    yield
    socket.getaddrinfo = _original_getaddrinfo
