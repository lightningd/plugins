import pytest


def pytest_addoption(parser):
    parser.addoption("--plugin", action="store", help="plugin name to pass to test")


@pytest.fixture
def plugin_name(request):
    return request.config.getoption("--plugin")
