"""Tests for hello_world.py."""

from hello_world import get_goodbye_message, get_hello_world_message


def test_get_hello_world_message() -> None:
    """Verify hello world message content."""
    assert get_hello_world_message() == "Hello, World!"


def test_get_goodbye_message() -> None:
    """Verify goodbye message content."""
    assert get_goodbye_message() == "Goodbye!"
