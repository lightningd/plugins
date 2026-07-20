import pytest

from clnutils import cln_parse_rpcversion


@pytest.mark.parametrize(
    "version, expected",
    [
        ("v25.09", [25, 9, 0]),
        ("v26.06.1", [26, 6, 1]),
        ("v26.06rc2", [26, 6, 0]),
        ("v26.06.1-custom", [26, 6, 1]),
        ("opencode/spenderp-defer-awaiting-recovery", None),
        ("v25", None),
        (None, None),
    ],
)
def test_cln_parse_rpcversion(version, expected):
    assert cln_parse_rpcversion(version) == expected
