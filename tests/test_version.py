"""Version / package metadata tests."""

from codehub import __version__


def test_version_is_semver_like() -> None:
    parts = __version__.split(".")
    assert len(parts) >= 2
    assert all(p.isdigit() for p in parts[:2])
    assert __version__ == "0.3.0"
