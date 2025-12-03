import pytest


@pytest.mark.parametrize(
    "a,b,expected",
    [
        # Simple positives
        *[(i, i + 1, 2 * i + 1) for i in range(50)],
        # Simple negatives
        *[(-i, -(i + 1), -(2 * i + 1)) for i in range(50)],
        # Mixed signs
        *[(i, -i, 0) for i in range(50)],
        # Edge-ish values
        (0, 0, 0),
        (1, -2, -1),
        (-1, 2, 1),
        (123, 456, 579),
        (-123, -456, -579),
    ],
)
def test_arithmetic_addition_sanity(a, b, expected):
    """Simple arithmetic sanity checks.

    These are synthetic tests meant to bulk‑exercise the test runner and
    demonstrate many passing cases (e.g. for CI load / coverage demos), not
    to validate application business logic.
    """
    assert a + b == expected


