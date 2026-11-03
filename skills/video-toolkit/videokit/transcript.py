"""Scribe-compatible transcript JSON, the format video-use's helpers read.

A transcript is {"language_code", "engine", "text", "words": [...]} where
each word is {"type": "word"|"spacing", "text", "start", "end", "speaker_id"}.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

DEFAULT_PROMPT = "Hum, é, tipo, né, então... pato amarelo."  # keeps fillers + the cut keyword verbatim
SPEAKER = "speaker_0"


def scribe_words(words: Iterable[dict]) -> list[dict]:
    """Turn {text, start, end, ...extra} words into Scribe words with spacing between them."""
    out: list[dict] = []
    prev_end = None
    for w in words:
        text = (w.get("text") or "").strip()
        if not text:
            continue
        start, end = float(w["start"]), float(w["end"])
        if prev_end is not None and start > prev_end:
            out.append({"type": "spacing", "text": " ", "start": round(prev_end, 3),
                        "end": round(start, 3), "speaker_id": SPEAKER})
        extra = {k: v for k, v in w.items() if k not in {"text", "start", "end"}}
        out.append({"type": "word", "text": text, "start": round(start, 3), "end": round(end, 3),
                    "speaker_id": SPEAKER, **extra})
        prev_end = end
    return out


def transcript_path(edit_dir: Path, stem: str) -> Path:
    return edit_dir / "transcripts" / f"{stem}.json"


def write_transcript(path: Path, engine: str, language: str | None, words: list[dict], **extra) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"language_code": language, "engine": engine,
               "text": " ".join(w["text"] for w in words if w["type"] == "word"),
               "words": words, **extra}
    # ASCII-escaped so pack_transcripts.py (reads with the locale codec on Windows) never chokes on accents
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def load_words(path: Path, only_words: bool = False) -> list[dict]:
    words = json.loads(path.read_text(encoding="utf-8-sig")).get("words", [])
    return [w for w in words if w.get("type", "word") == "word"] if only_words else words


def count_words(words: list[dict]) -> int:
    return sum(w.get("type", "word") == "word" for w in words)
