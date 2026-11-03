"""Check or save the Groq/OpenAI key mediacript uses for transcription.

Thin wrapper over `mediacript config`, resolved the same way the transcriber
resolves the CLI (MEDIACRIPT_CLI, local clone, or npx). Keys are never printed.

Usage:
    python mediacript_key.py status            # JSON: which keys are configured
    python mediacript_key.py set groq <key>    # validates the key with the provider, then saves it
    python mediacript_key.py unset groq

Get a Groq key at https://console.groq.com/keys.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videokit.mediacript import run_cli  # noqa: E402


def main() -> None:
    args = sys.argv[1:] or ["status"]
    if args[0] in {"-h", "--help"}:
        print(__doc__)
        return
    proc = run_cli(["config", *args])
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
