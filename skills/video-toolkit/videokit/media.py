"""ffmpeg/ffprobe runners and media file discovery."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS


def list_media(path: Path, exts: set[str] = MEDIA_EXTS) -> tuple[list[Path], Path]:
    """Files to process and their base dir: the dir itself, or a single file and its parent."""
    src = path.resolve()
    if src.is_dir():
        files = sorted(p for p in src.iterdir() if p.suffix.lower() in exts)
        base = src
    elif src.exists():
        files, base = [src], src.parent
    else:
        sys.exit(f"not found: {src}")
    if not files:
        sys.exit(f"no media files in {src}")
    return files, base


def capture(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run and return the result without checking the exit code (ffmpeg logs go to stderr)."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def run(cmd: list[str], cwd: Path | None = None) -> None:
    """Run and exit with the command's stderr tail if it fails."""
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"{cmd[0]} failed:\n{' '.join(cmd)}\n{r.stderr[-2000:]}")


def probe_fps(src: Path, default: str = "30") -> str:
    """Video frame rate as ffprobe's fraction string (e.g. 30000/1001)."""
    out = capture(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                   "stream=r_frame_rate", "-of", "csv=p=0", str(src)]).stdout
    # some files print the stream line more than once
    lines = [ln.strip().rstrip(",") for ln in out.splitlines() if ln.strip()]
    return lines[0] if lines else default


def probe(video: Path) -> dict:
    """Duration, size, fps and orientation of the first video stream."""
    r = capture(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(video)])
    d = json.loads(r.stdout)
    s = d["streams"][0]
    num, den = (s["r_frame_rate"].split("/") + ["1"])[:2]
    return {"duration_s": round(float(d["format"]["duration"]), 2), "width": s["width"], "height": s["height"],
            "fps": round(float(num) / float(den or 1), 2),
            "orientation": "vertical" if s["height"] > s["width"] else "horizontal"}


def extract_audio(video: Path, dest: Path, audio_track: int = 0) -> None:
    """16 kHz mono PCM wav, the format Whisper expects."""
    run(["ffmpeg", "-y", "-i", str(video), "-map", f"0:a:{audio_track}",
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)])


def srt_ts(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
