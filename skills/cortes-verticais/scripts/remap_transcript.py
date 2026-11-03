"""Map raw-footage transcripts onto the edited final.mp4 timeline.

Avoids re-transcribing the final cut: walks edl.json ranges in order and
shifts each kept word to output time (word.start - range.start + offset).
Writes a Scribe-compatible JSON (words + spacing) for make_short.py.

Usage:
    python remap_transcript.py <edit_dir> [-o <edit_dir>/transcripts_final/final.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))

from videokit.transcript import count_words, load_words  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("edit_dir", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()

    edit = args.edit_dir.resolve()
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8-sig"))
    tdir = edit / "transcripts"
    cache: dict[str, list[dict]] = {}

    def words_for(src: str) -> list[dict]:
        if src not in cache:
            p = tdir / f"{src}.json"
            if not p.exists():
                # 2-file setups transcribe only one source; any transcript has the same audio
                found = sorted(tdir.glob("*.json"))
                if not found:
                    sys.exit(f"no transcripts in {tdir}")
                p = found[0]
            cache[src] = load_words(p, only_words=True)
        return cache[src]

    out_words: list[dict] = []
    offset = 0.0
    prev_end = None
    for r in edl["ranges"]:
        a, b = float(r["start"]), float(r["end"])
        for w in words_for(r["source"]):
            if w["end"] <= a or w["start"] >= b:
                continue
            s = round(max(w["start"], a) - a + offset, 3)
            e = round(min(w["end"], b) - a + offset, 3)
            if prev_end is not None and s > prev_end:
                out_words.append({"type": "spacing", "text": " ", "start": prev_end, "end": s})
            out_words.append({**w, "start": s, "end": e})
            prev_end = e
        offset += b - a

    out = args.output or (edit / "transcripts_final" / "final.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"engine": "remapped-from-edl", "words": out_words}, ensure_ascii=True, indent=1),
                   encoding="utf-8")
    n = count_words(out_words)
    print(f"remapped {n} words over {offset:.1f}s -> {out}")


if __name__ == "__main__":
    main()
