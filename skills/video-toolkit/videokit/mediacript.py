"""Cloud transcription through the mediacript CLI (Groq whisper-large-v3, OpenAI fallback).

mediacript extracts a 16 kHz mono track, splits it at quiet points when it
exceeds the per-request size limit (10 MB), transcribes chunks in parallel and
re-sends stretches that came back empty despite audible sound.

Needs node + ffmpeg on PATH and a Groq/OpenAI key: GROQ_API_KEY, or saved in
mediacript's config with scripts/mediacript_key.py (`mediacript config set`).
A missing key raises MissingKeyError instead of falling back to local Whisper.

Which CLI runs, first match wins:
  1. MEDIACRIPT_CLI=<path to cli.mjs>  (explicit override)
  2. ~/code/mediacript/packages/cli/cli.mjs  (local dev clone, picks up unpublished changes)
  3. npx -y mediacript@^MIN_VERSION  (published package; downloaded and cached on first use)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .transcript import count_words, scribe_words, write_transcript

DEV_CLI = Path.home() / "code" / "mediacript" / "packages" / "cli" / "cli.mjs"
MIN_VERSION = "1.2.42"  # first release with `config set` and exit code 3 for a missing key
EXIT_NO_KEY = 3
KEYS_URL = "https://console.groq.com/keys"


class MissingKeyError(RuntimeError):
    """No Groq/OpenAI key configured: a setup problem, not a transient failure, so it is never
    silently replaced by the slow local fallback."""

    def __init__(self) -> None:
        super().__init__(
            "no Groq/OpenAI API key configured for mediacript.\n"
            f"  Get a Groq key at {KEYS_URL} (free tier available) and save it with:\n"
            "    python ~/.claude/skills/video-toolkit/scripts/mediacript_key.py set groq <key>\n"
            "  or set the GROQ_API_KEY environment variable.\n"
            "  To transcribe locally instead (slow), pass --engine whisper."
        )


def cli_command() -> list[str]:
    override = os.environ.get("MEDIACRIPT_CLI")
    if override:
        if not Path(override).exists():
            raise RuntimeError(f"MEDIACRIPT_CLI points to a missing file: {override}")
        return ["node", override]
    if DEV_CLI.exists():
        return ["node", str(DEV_CLI)]
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx not found on PATH (install Node.js) and no local mediacript clone")
    return [npx, "-y", f"mediacript@^{MIN_VERSION}"]


def run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([*cli_command(), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def key_status() -> dict | None:
    """`mediacript config status` as a dict, or None if the CLI can't report it (older version)."""
    proc = run_cli(["config", "status"])
    try:
        return json.loads(proc.stdout) if proc.returncode == 0 else None
    except json.JSONDecodeError:
        return None


def ensure_key() -> None:
    status = key_status()
    if status is not None and not status.get("transcriptionReady"):
        raise MissingKeyError()


def run_mediacript(video: Path, language: str | None, prompt: str | None) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.json"
        cmd = [*cli_command(), "transcribe", str(video), "--words", "-o", str(out)]
        if language:
            cmd += ["--language", language]
        if prompt:
            cmd += ["--prompt", prompt]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode == EXIT_NO_KEY:
            raise MissingKeyError()
        if proc.returncode != 0 or not out.exists():
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-5:])
            raise RuntimeError(f"mediacript exited {proc.returncode}: {tail}")
        return json.loads(out.read_text(encoding="utf-8"))


def transcribe_to(video: Path, out: Path, language: str | None, prompt: str | None) -> str:
    t0 = time.time()
    result = run_mediacript(video, language, prompt)
    words = scribe_words({"text": w.get("word"), "start": w["start"], "end": w["end"]}
                         for w in result.get("words", []))
    write_transcript(out, "mediacript", language or result.get("language"), words,
                     chunks=result.get("chunks"), recovered_gaps=result.get("recoveredGaps"))
    chunks = len(result.get("chunks") or [])
    return f"saved ({count_words(words)} words, {chunks} chunk(s)) in {time.time() - t0:.0f}s"
