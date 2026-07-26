"""Hello and goodbye message application."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MessageError(Exception):
    """Raised when generating an application message fails."""


def get_hello_world_message() -> str:
    """Return the hello world message.

    Returns:
        Hello world message.
    """
    try:
        return "Hello, World!"
    except Exception as exc:
        logger.exception("Failed to build hello world message")
        raise MessageError("Unable to create hello world message") from exc


def get_goodbye_message() -> str:
    """Return the goodbye message.

    Returns:
        Goodbye message.
    """
    try:
        return "Goodbye!"
    except Exception as exc:
        logger.exception("Failed to build goodbye message")
        raise MessageError("Unable to create goodbye message") from exc


def main() -> None:
    """Application entrypoint."""
    print(get_hello_world_message())
    print(get_goodbye_message())


if __name__ == "__main__":
    main()
