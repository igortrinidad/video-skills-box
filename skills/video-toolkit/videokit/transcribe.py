"""Transcribe many files: mediacript first (parallel), local Whisper for whatever failed.

Cached: a source whose transcript already exists is skipped.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import mediacript, whisper_local
from .transcript import DEFAULT_PROMPT, transcript_path

ENGINES = ("auto", "mediacript", "whisper")


def transcribe_all(files: list[Path], edit_dir: Path, language: str | None = "pt",
                   prompt: str | None = DEFAULT_PROMPT, engine: str = "auto", jobs: int = 3,
                   whisper_model: str = "small", threads: int | None = None) -> list[Path]:
    """Writes <edit_dir>/transcripts/<stem>.json for each file. Returns the files that still failed.

    engine: auto = mediacript, then local Whisper for failures; mediacript = no fallback;
    whisper = local only.
    Raises mediacript.MissingKeyError when no Groq/OpenAI key is configured (never falls back for that).
    """
    t0 = time.time()
    todo = []
    for f in files:
        if transcript_path(edit_dir, f.stem).exists():
            print(f"  {f.name}: cached", flush=True)
        else:
            todo.append(f)

    failed: list[Path] = list(todo) if engine == "whisper" else []
    if engine != "whisper" and todo:
        # Checked once up front so a missing key stops here instead of sending every file to local Whisper
        mediacript.ensure_key()

        def work(video: Path) -> None:
            try:
                status = mediacript.transcribe_to(video, transcript_path(edit_dir, video.stem), language, prompt)
                print(f"  {video.name}: {status}", flush=True)
            except mediacript.MissingKeyError:
                raise
            except Exception as e:  # noqa: BLE001 - any other failure goes to the fallback
                print(f"  {video.name}: mediacript failed: {e}", flush=True)
                failed.append(video)

        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            list(pool.map(work, todo))

    if failed and engine != "mediacript":
        print(f"  local Whisper ({whisper_model}) for {len(failed)} file(s)", flush=True)
        model = whisper_local.load_model(whisper_model, threads or os.cpu_count() or 4)
        for video in sorted(failed):
            status = whisper_local.transcribe_to(model, video, transcript_path(edit_dir, video.stem), language,
                                                 prompt=prompt)
            print(f"  {video.name}: {status}", flush=True)
        failed = []

    print(f"transcripts done in {time.time() - t0:.0f}s -> {edit_dir / 'transcripts'}", flush=True)
    return failed
