"""Transcribe videos to Scribe-compatible JSON in <edit_dir>/transcripts/<stem>.json.

Same format as video-use's transcribe.py, so pack_transcripts.py, timeline_view.py
and render.py work unchanged.

Default engine (auto): mediacript via Groq (a 57 min talk takes ~1 min, 3 files at
a time); files that fail there (no network, quota, missing key) fall back to local
faster-whisper on CPU (slow). Cached: existing transcripts are never redone.

No Groq/OpenAI key configured: exits with code 3 (MISSING_API_KEY) without
transcribing; save one with mediacript_key.py, or pass --engine whisper.

Usage:
    python transcribe.py <video_or_dir> [--edit-dir DIR] [--language pt] [--prompt TEXT]
        [--engine auto|mediacript|whisper] [--jobs 3] [--whisper-model small]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videokit.cli import run_main  # noqa: E402
from videokit.media import list_media  # noqa: E402
from videokit.transcribe import ENGINES, transcribe_all  # noqa: E402
from videokit.transcript import DEFAULT_PROMPT  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcription to Scribe-compatible JSON (Groq, local fallback)")
    ap.add_argument("path", type=Path, help="video file or directory of videos")
    ap.add_argument("--edit-dir", type=Path, default=None, help="default: <dir>/edit")
    ap.add_argument("--language", default="pt")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT,
                    help="Whisper prompt that keeps fillers and the keyword verbatim ('' to disable)")
    ap.add_argument("--engine", choices=ENGINES, default="auto",
                    help="auto: mediacript then local fallback; mediacript: no fallback; whisper: local only")
    ap.add_argument("--jobs", type=int, default=3, help="files sent to mediacript at the same time")
    ap.add_argument("--whisper-model", default="small",
                    help="local model: small (faster), medium (better PT), large-v3 (best, slow)")
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4, help="CPU threads for local Whisper")
    args = ap.parse_args()

    files, base = list_media(args.path)
    edit_dir = (args.edit_dir or base / "edit").resolve()
    failed = transcribe_all(files, edit_dir, args.language or None, args.prompt or None, args.engine,
                            args.jobs, args.whisper_model, args.threads)
    if failed:
        sys.exit(f"failed: {', '.join(f.name for f in failed)}")


if __name__ == "__main__":
    run_main(main)
