"""Entry-point wrapper shared by skill scripts that transcribe."""

from __future__ import annotations

import sys
from collections.abc import Callable

from .mediacript import EXIT_NO_KEY, MissingKeyError


def run_main(main: Callable[[], None]) -> None:
    """Exit with code 3 and setup instructions when no transcription key is configured,
    so the agent can ask the user for one instead of reading a traceback."""
    try:
        main()
    except MissingKeyError as e:
        print(f"MISSING_API_KEY: {e}", file=sys.stderr)
        sys.exit(EXIT_NO_KEY)
