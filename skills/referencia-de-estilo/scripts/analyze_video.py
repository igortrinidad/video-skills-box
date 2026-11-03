"""Measure the editing style of a video so it can be imitated or compared.

For each video writes <out>/<stem>/:
  metrics.json       - duration, shots/min, shot lengths, speech pace, pauses kept, loudness
  scenes.json        - detected cut times
  contact_sheet.png  - one labelled frame per shot (sampled), for visual reading
  transcripts/       - cached transcript (Scribe-compatible; Groq via mediacript, local Whisper fallback)

Usage:
  python analyze_video.py <video_or_dir> [--out DIR] [--scene 0.25] [--engine auto] [--no-transcribe]
  python analyze_video.py --compare ref/metrics.json final/metrics.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))

from videokit.cli import run_main  # noqa: E402
from videokit.media import VIDEO_EXTS, capture as sh, list_media, probe  # noqa: E402
from videokit.transcribe import ENGINES, transcribe_all  # noqa: E402
from videokit.transcript import load_words, transcript_path  # noqa: E402


def detect_cuts(video: Path, threshold: float) -> list[float]:
    r = sh(["ffmpeg", "-hide_banner", "-i", str(video), "-an", "-vf",
            f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"])
    return [round(float(t), 2) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def loudness(video: Path) -> float | None:
    r = sh(["ffmpeg", "-hide_banner", "-i", str(video), "-vn", "-af", "ebur128", "-f", "null", "-"])
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else None


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return round(v[min(len(v) - 1, int(p * (len(v) - 1) + 0.5))], 3)


def speech_metrics(words: list[dict], duration: float) -> dict:
    ws = [w for w in words if w.get("type", "word") == "word"]
    if len(ws) < 2:
        return {"words": len(ws)}
    gaps = [max(0.0, b["start"] - a["end"]) for a, b in zip(ws, ws[1:])]
    spoken = sum(w["end"] - w["start"] for w in ws)
    minutes = duration / 60
    return {
        "words": len(ws),
        "words_per_min": round(len(ws) / minutes, 1),
        "speech_ratio": round(spoken / duration, 3),
        "pause_p50_s": pct(gaps, 0.5),
        "pause_p90_s": pct(gaps, 0.9),
        "pause_max_s": round(max(gaps), 2),
        "pauses_over_0_5s_per_min": round(sum(g >= 0.5 for g in gaps) / minutes, 2),
        "pauses_over_1s_per_min": round(sum(g >= 1.0 for g in gaps) / minutes, 2),
        "lead_in_s": round(ws[0]["start"], 2),
        "tail_s": round(duration - ws[-1]["end"], 2),
    }


def contact_sheet(video: Path, shots: list[tuple[float, float]], out: Path, max_frames: int) -> int:
    from PIL import Image, ImageDraw

    if len(shots) > max_frames:
        step = len(shots) / max_frames
        shots = [shots[int(i * step)] for i in range(max_frames)]
    tiles = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, (a, b) in enumerate(shots):
            t = (a + b) / 2
            f = Path(tmp) / f"{i:03d}.jpg"
            sh(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                "-vf", "scale=320:-2", "-q:v", "4", str(f)])
            if f.exists():
                im = Image.open(f).convert("RGB")
                d = ImageDraw.Draw(im)
                label = f"#{i + 1} {int(a // 60)}:{a % 60:04.1f} ({b - a:.1f}s)"
                d.rectangle([0, 0, 8 + 7 * len(label), 16], fill=(0, 0, 0))
                d.text((4, 2), label, fill=(255, 255, 0))
                tiles.append(im)
    if not tiles:
        return 0
    tw = max(t.width for t in tiles)
    th = max(t.height for t in tiles)
    cols = 4 if tiles[0].height > tiles[0].width else 5
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), (30, 30, 30))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
    sheet.save(out, quality=85)
    return len(tiles)


def transcribe(video: Path, out_dir: Path, engine: str, model_name: str) -> list[dict]:
    if transcribe_all([video], out_dir, engine=engine, whisper_model=model_name):
        sys.exit(f"transcription failed for {video.name}")
    return load_words(transcript_path(out_dir, video.stem))


def analyze(video: Path, out_root: Path, threshold: float, engine: str, model: str, do_transcribe: bool,
            max_frames: int) -> Path:
    out = out_root / video.stem
    out.mkdir(parents=True, exist_ok=True)
    print(f"== {video.name}")
    info = probe(video)
    dur = info["duration_s"]

    print("  detecting cuts...", flush=True)
    cuts = detect_cuts(video, threshold)
    bounds = [0.0] + [c for c in cuts if 0.2 < c < dur - 0.2] + [dur]
    shots = [(a, b) for a, b in zip(bounds, bounds[1:]) if b - a > 0.05]
    lens = [b - a for a, b in shots]
    (out / "scenes.json").write_text(json.dumps({"threshold": threshold, "cuts": cuts}, indent=1))

    metrics = {
        "video": str(video),
        **info,
        "scene_threshold": threshold,
        "shots": len(shots),
        "shots_per_min": round(len(shots) / (dur / 60), 2),
        "shot_len_median_s": round(st.median(lens), 2),
        "shot_len_mean_s": round(st.mean(lens), 2),
        "shot_len_min_s": round(min(lens), 2),
        "shot_len_max_s": round(max(lens), 2),
        "loudness_lufs": loudness(video),
    }

    if do_transcribe:
        print("  transcribing...", flush=True)
        metrics["speech"] = speech_metrics(transcribe(video, out, engine, model), dur)

    print("  contact sheet...", flush=True)
    metrics["contact_sheet_frames"] = contact_sheet(video, shots, out / "contact_sheet.png", max_frames)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return out


def flatten(d: dict, prefix: str = "") -> dict:
    flat = {}
    for k, v in d.items():
        if isinstance(v, dict):
            flat.update(flatten(v, f"{prefix}{k}."))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            flat[f"{prefix}{k}"] = v
    return flat


def compare(ref_path: Path, out_path: Path) -> None:
    ref = flatten(json.loads(ref_path.read_text(encoding="utf-8")))
    got = flatten(json.loads(out_path.read_text(encoding="utf-8")))
    print(f"{'metric':34s} {'referencia':>12s} {'editado':>12s} {'diff':>8s}")
    for k in ref:
        if k in got and k not in {"width", "height", "scene_threshold", "contact_sheet_frames"}:
            r, g = ref[k], got[k]
            diff = f"{(g - r) / r * 100:+.0f}%" if r else "-"
            print(f"{k:34s} {r:12} {g:12} {diff:>8s}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path, nargs="?")
    ap.add_argument("--out", type=Path, default=None, help="default: <dir>/_analise")
    ap.add_argument("--scene", type=float, default=0.25,
                    help="scene-change threshold; lower (0.1-0.15) catches jump cuts on talking heads")
    ap.add_argument("--engine", choices=ENGINES, default="auto",
                    help="transcription engine for pace metrics (auto: Groq, local Whisper fallback)")
    ap.add_argument("--model", default="small", help="local whisper model, used only on fallback/--engine whisper")
    ap.add_argument("--no-transcribe", action="store_true")
    ap.add_argument("--max-frames", type=int, default=40)
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("REF_METRICS", "EDIT_METRICS"))
    args = ap.parse_args()

    if args.compare:
        compare(*args.compare)
        return
    if not args.path:
        ap.error("path required")
    videos, base = list_media(args.path, VIDEO_EXTS)
    out_root = (args.out or base / "_analise").resolve()
    for v in videos:
        analyze(v, out_root, args.scene, args.engine, args.model, not args.no_transcribe, args.max_frames)


if __name__ == "__main__":
    run_main(main)
