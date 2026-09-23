"""Tests for the server↔TV subnet-mismatch hint."""

from birdscreen.web.app import _different_subnet


def test_same_subnet_is_not_a_mismatch() -> None:
    assert _different_subnet("192.168.1.5", "192.168.1.219") is False


def test_different_subnet_is_a_mismatch() -> None:
    # The guest-network case: server jumped to 192.168.2.x, TV stayed on .1.x.
    assert _different_subnet("192.168.2.5", "192.168.1.219") is True


def test_no_server_ip_never_warns() -> None:
    assert _different_subnet(None, "192.168.1.219") is False


def test_hostname_tv_never_warns() -> None:
    # A non-IP TV address (hostname) can't be compared → no false alarm.
    assert _different_subnet("192.168.2.5", "frame.local") is False
