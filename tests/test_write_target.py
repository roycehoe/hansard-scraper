import pytest

from exceptions import HansardWriteTargetError
from utils.write_target import validate_can_write


def test_a_local_url_on_port_0_is_refused() -> None:
    with pytest.raises(HansardWriteTargetError):
        validate_can_write("postgresql://user:password@localhost:0/anything")


def test_a_local_url_without_a_port_is_refused() -> None:
    with pytest.raises(HansardWriteTargetError):
        validate_can_write("postgresql://user:password@localhost/anything")


def test_a_local_url_on_the_scratch_port_is_allowed() -> None:
    validate_can_write("postgresql://user:password@localhost:5435/anything")


def test_the_loop_copy_is_refused_on_any_host() -> None:
    with pytest.raises(HansardWriteTargetError):
        validate_can_write("postgresql://user:password@db.example.org:6543/hansard_w3")
