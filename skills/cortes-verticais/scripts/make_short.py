"""Build one vertical 1080x1920 short from a horizontal video.

Driven by a JSON spec so the agent decides content and layout, and this
script handles the ffmpeg details (crop/stack, 30ms fades, concat, captions,
loudness).

Spec (paths may be relative to the spec file):
{
  "source": "../edit/final.mp4",
  "transcript": "transcripts/final.json",      # Scribe/Whisper JSON, optional
  "output": "shorts/01-nome-do-corte.mp4",
  "boxes": {                                    # crop boxes in SOURCE pixels: x,y,w,h
    "face":   [1300, 80, 560, 1000],            # used by face / stack
    "screen": [0, 0, 1280, 1080]                # used by stack
  },
  "segments": [
    {"start": 120.40, "end": 131.90, "layout": "face"},
    {"start": 131.90, "end": 175.20, "layout": "stack"},
    {"start": 190.00, "end": 201.50, "layout": "fit"}
  ],
  "captions": true,
  "caption_margin": 0.30,     # caption baseline height as fraction of frame from bottom
  "hook": "Texto opcional no topo nos 3 primeiros segundos"
}

Layouts:
  face   - crop the face box, scale/pad to fill 1080x1920 (cover).
  stack  - screen box on top (1080 wide), face box below filling the rest.
  fit    - whole frame scaled to 1080 wide over a blurred, zoomed copy of itself.

Usage: python make_short.py spec.json [--preview]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))

from videokit.media import probe_fps, run, srt_ts  # noqa: E402
from videokit.transcript import load_words  # noqa: E402

W, H = 1080, 1920
PUNCT = set(".,!?;:")


def even(v: float) -> int:
    return int(v) // 2 * 2


def crop(box) -> str:
    x, y, w, h = (even(v) for v in box)
    return f"crop={w}:{h}:{x}:{y}"


def cover(w: int, h: int) -> str:
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"


def layout_filter(layout: str, boxes: dict) -> str:
    if layout == "face":
        return f"[0:v]{crop(boxes['face'])},{cover(W, H)},setsar=1[v]"
    if layout == "stack":
        sx, sy, sw, sh = boxes["screen"]
        top_h = even(W * sh / sw)
        if top_h > H * 0.6:
            top_h = even(H * 0.6)
        bot_h = H - top_h
        return (f"[0:v]split[a][b];"
                f"[a]{crop(boxes['screen'])},{cover(W, top_h)}[top];"
                f"[b]{crop(boxes['face'])},{cover(W, bot_h)}[bot];"
                f"[top][bot]vstack,setsar=1[v]")
    if layout == "fit":
        return (f"[0:v]split[a][b];"
                f"[a]{cover(W, H)},boxblur=30:3,eq=brightness=-0.08[bg];"
                f"[b]scale={W}:-2[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")
    sys.exit(f"unknown layout: {layout}")


def build_srt(words: list[dict], segments: list[dict]) -> str:
    cues = []
    offset = 0.0
    for seg in segments:
        a, b = seg["start"], seg["end"]
        ws = [w for w in words if w.get("type", "word") == "word"
              and w["end"] > a and w["start"] < b and w.get("text", "").strip()]
        chunk: list[dict] = []
        for i, w in enumerate(ws):
            chunk.append(w)
            nxt = ws[i + 1] if i + 1 < len(ws) else None
            gap = nxt["start"] - w["end"] if nxt else 0
            dur = w["end"] - chunk[0]["start"]
            if (nxt is None or w["text"].strip()[-1] in PUNCT or gap >= 0.3
                    or len(chunk) >= 3 or (len(chunk) >= 2 and dur >= 0.35)):
                s = max(chunk[0]["start"], a) - a + offset
                e = min(chunk[-1]["end"], b) - a + offset
                text = re.sub(r"\s+", " ", " ".join(x["text"].strip() for x in chunk)).rstrip(",;:").upper()
                cues.append((s, max(e, s + 0.3), text))
                chunk = []
        offset += b - a
    return "\n".join(f"{i}\n{srt_ts(s)} --> {srt_ts(e)}\n{t}\n" for i, (s, e, t) in enumerate(cues, 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", type=Path)
    ap.add_argument("--preview", action="store_true", help="faster encode for checking")
    args = ap.parse_args()

    spec_path = args.spec.resolve()
    base = spec_path.parent
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    rel = lambda p: (base / p).resolve()  # noqa: E731

    src = rel(spec["source"])
    out = rel(spec["output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    boxes = spec.get("boxes", {})
    segs = spec["segments"]
    fps = probe_fps(src)
    preset, crf = ("veryfast", "24") if args.preview else ("medium", "20")

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        parts = []
        for i, seg in enumerate(segs):
            dur = seg["end"] - seg["start"]
            part = tmp / f"p{i:02d}.mp4"
            run(["ffmpeg", "-y", "-ss", f"{seg['start']:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
                 "-filter_complex", layout_filter(seg.get("layout", "fit"), boxes), "-map", "[v]", "-map", "0:a:0",
                 "-af", f"afade=t=in:d=0.03,afade=t=out:st={max(dur - 0.03, 0):.3f}:d=0.03",
                 "-r", fps, "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(part)])
            parts.append(part)
            print(f"  [{i:02d}] {seg.get('layout', 'fit'):5s} {seg['start']:8.2f}-{seg['end']:8.2f} ({dur:.1f}s)")

        (tmp / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts))
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "joined.mp4"], cwd=tmp)

        vf = []
        if spec.get("captions", True) and spec.get("transcript"):
            words = load_words(rel(spec["transcript"]))
            (tmp / "subs.srt").write_text(build_srt(words, segs), encoding="utf-8")
            margin = int(288 * spec.get("caption_margin", 0.30))
            style = ("FontName=Arial,FontSize=13,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                     f"BorderStyle=1,Outline=1.6,Shadow=0,Alignment=2,MarginV={margin}")
            vf.append(f"subtitles=subs.srt:force_style='{style}'")
        if spec.get("hook"):
            (tmp / "hook.txt").write_text(spec["hook"], encoding="utf-8")
            vf.append("drawtext=textfile=hook.txt:fontfile='C\\:/Windows/Fonts/arialbd.ttf':fontsize=64:"
                      "fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=24:x=(w-tw)/2:y=h*0.08:"
                      "enable='lt(t,3)'")

        enc = ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p"]
        af = "loudnorm=I=-14:TP=-1:LRA=11"
        cmd = ["ffmpeg", "-y", "-i", "joined.mp4"]
        cmd += (["-vf", ",".join(vf)] + enc) if vf else ["-c:v", "copy"]
        cmd += ["-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "out.mp4"]
        run(cmd, cwd=tmp)
        shutil.move(str(tmp / "out.mp4"), out)

    total = sum(s["end"] - s["start"] for s in segs)
    print(f"done: {out} ({total:.1f}s, {len(segs)} segment(s))")


if __name__ == "__main__":
    main()
