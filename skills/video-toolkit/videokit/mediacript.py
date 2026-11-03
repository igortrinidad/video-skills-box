"""Cloud transcription through the mediacript CLI (Groq whisper-large-v3, OpenAI fallback).

mediacript extracts a 16 kHz mono track, splits it at quiet points when it
exceeds the per-request size limit (10 MB), transcribes chunks in parallel and
re-sends stretches that came back empty despite audible sound.

Needs node + ffmpeg on PATH and a Groq/OpenAI key in mediacript's config
(%APPDATA%/ffmpeg-simple-converter/config.json). The CLI location defaults to
~/code/mediacript/packages/cli/cli.mjs; override with MEDIACRIPT_CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from .transcript import count_words, scribe_words, write_transcript

DEFAULT_CLI = Path.home() / "code" / "mediacript" / "packages" / "cli" / "cli.mjs"


def cli_path() -> Path:
    return Path(os.environ.get("MEDIACRIPT_CLI") or DEFAULT_CLI)


def run_mediacript(video: Path, language: str | None, prompt: str | None) -> dict:
    cli = cli_path()
    if not cli.exists():
        raise RuntimeError(f"mediacript CLI not found at {cli} (set MEDIACRIPT_CLI)")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.json"
        cmd = ["node", str(cli), "transcribe", str(video), "--words", "-o", str(out)]
        if language:
            cmd += ["--language", language]
        if prompt:
            cmd += ["--prompt", prompt]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
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
