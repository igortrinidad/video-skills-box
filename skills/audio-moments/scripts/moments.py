"""Find the moments a transcript misses: applause, cheering, laughter, shouting and bursts of excitement.

Three signals, all local:
  - sound events: a model trained on AudioSet (PANNs Cnn14) scores applause, cheering, laughter, crowd... per frame;
  - loudness: bursts well above the usual speaking level of the clip and of the whole project;
  - the transcript: shouted words ("AAAAH!", "Uuuu"), chants ("Ola! Ola! Ola!"), celebration words ("parabéns").
A moment where several agree is almost always real.

The model runs once per clip and its curves are cached; detection happens when the report is built, so the
thresholds can change without analysing the audio again.

    edit/moments/clips/<clip>.json   curves of one clip every 0.25 s (cache, keyed by the file fingerprint)
    edit/moments/moments.md          every moment of the project, strongest first, with the words around it
    edit/moments/moments.json        the same, for other scripts

Usage:
    python moments.py setup                                  download the model (~330 MB, once)
    python moments.py scan <project|file> [--jobs 2] [--min-score 0.4] [--redo]
    python moments.py report <project|file> [--min-score 0.4]   rebuild the report from the cache
    python moments.py status <project|file>
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))

from videokit.media import MEDIA_EXTS  # noqa: E402
from videokit.project import raw_dir  # noqa: E402
from videokit.transcript import load_words, transcript_path  # noqa: E402

VERSION = 2  # bump when the cached curves change, so clips are analysed again
SR = 32000
FPS = 100  # PANNs frame rate (hop 320 at 32 kHz)
STEP_S = 0.25  # resolution of the cached curves
CHUNK_S = 30
MODEL_DIR = Path.home() / "panns_data"
MODEL = MODEL_DIR / "Cnn14_DecisionLevelMax.pth"
# Same checkpoint as zenodo.org/record/3987831 (Cnn14_DecisionLevelMax_mAP=0.385), which is too slow to download
MODEL_URL = "https://huggingface.co/spaces/pauldarvin/wav_SED/resolve/main/panns_data/Cnn14_DecisionLevelMax.pth"
MODEL_MIN_BYTES = 300_000_000
LABELS = MODEL_DIR / "class_labels_indices.csv"
LABELS_URL = ("https://raw.githubusercontent.com/qiuqiangkong/audioset_tagging_cnn/master/"
              "metadata/class_labels_indices.csv")

# AudioSet classes grouped into what an editor cares about.
# In handheld footage the voice next to the camera dominates, so a real crowd cheer often scores only 0.1-0.2:
# thresholds are low on purpose, and loudness and the transcript confirm.
GROUPS = {
    "applause": {"classes": ["Applause", "Clapping"], "threshold": 0.12, "weight": 1.0},
    "cheering": {"classes": ["Cheering", "Whoop", "Yell", "Shout", "Screaming", "Children shouting", "Bellow",
                             "Battle cry"], "threshold": 0.12, "weight": 1.0},
    "laughter": {"classes": ["Laughter", "Giggle", "Chuckle, chortle", "Belly laugh", "Snicker", "Baby laughter"],
                 "threshold": 0.12, "weight": 0.9},
    "crying": {"classes": ["Crying, sobbing", "Whimper", "Wail, moan"], "threshold": 0.15, "weight": 0.8},
    "crowd": {"classes": ["Crowd"], "threshold": 0.20, "weight": 0.5},
    "singing": {"classes": ["Singing", "Choir", "Chant"], "threshold": 0.25, "weight": 0.4},
    "music": {"classes": ["Music"], "threshold": 0.40, "weight": 0.0},
}
SOUND_MOMENTS = ["applause", "cheering", "laughter", "crying", "crowd"]  # the rest only describe the scene
SMOOTH_S = 0.5
MIN_EVENT_S = 0.5
MERGE_GAP_S = 2.0
LOUD_RISE_DB = 8.0  # above the usual speaking level
CONTEXT_BEFORE_S = 8.0  # what was said right before applause is usually the reason for it
CONTEXT_AFTER_S = 3.0

# Words that carry excitement in Brazilian Portuguese (compared without accents, lowercase)
# Only words that are rare in ordinary talk; "obrigado", "demais", "legal" are said all the time and are left out
EXCITED_WORDS = {
    "parabens", "uhul", "uhuu", "aee", "eita", "caramba", "uau", "meu deus", "aleluia", "deu bom",
    "conseguimos", "ganhamos", "ganhou", "campeao", "campea", "primeiro lugar", "que massa", "incrivel",
    "sensacional", "absurdo", "chora", "zerei a vida",
}

# Words people repeat in normal speech; three in a row is not a chant
CALM_REPEATS = {"nao", "sim", "eu", "e", "a", "o", "que", "ne", "tipo", "isso", "ta", "so", "calma", "ai", "uma", "um"}


def dump(obj) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def clock(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def plain(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ---------- model ----------

def download(url: str, dest: Path, min_bytes: int = 0) -> None:
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {dest.name}...", flush=True)
    r = subprocess.run(["curl", "-L", "--retry", "8", "-s", "-o", str(dest), url])
    if r.returncode != 0 or not dest.exists():
        urllib.request.urlretrieve(url, dest)
    if dest.stat().st_size < min_bytes:
        sys.exit(f"download incomplete: {dest} ({dest.stat().st_size} bytes). Run `moments.py setup` again.")


def setup() -> dict:
    download(LABELS_URL, LABELS)
    download(MODEL_URL, MODEL, MODEL_MIN_BYTES)
    return {"model": str(MODEL), "bytes": MODEL.stat().st_size}


def load_model():
    setup()
    import torch
    from panns_inference.config import labels
    from panns_inference.models import Cnn14_DecisionLevelMax

    model = Cnn14_DecisionLevelMax(sample_rate=SR, window_size=1024, hop_size=320, mel_bins=64, fmin=50,
                                   fmax=14000, classes_num=len(labels), interpolate_mode="nearest")
    model.load_state_dict(torch.load(MODEL, map_location="cpu")["model"])
    model.eval()
    index = {g: [labels.index(c) for c in spec["classes"] if c in labels] for g, spec in GROUPS.items()}
    return model, index


# ---------- analysis (cached) ----------

def read_audio(src: Path) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-map", "0:a:0", "-vn", "-ac", "1",
                        "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def framewise(model, audio: np.ndarray) -> np.ndarray:
    """(frames, 527) probabilities, in chunks so long clips do not exhaust memory."""
    import torch

    step = CHUNK_S * SR
    out = []
    for i in range(0, len(audio), step):
        part = audio[i:i + step]
        chunk = np.pad(part, (0, max(0, SR - len(part))))
        with torch.no_grad():
            fw = model(torch.from_numpy(chunk[None, :]), None)["framewise_output"][0].numpy()
        out.append(fw[:int(round(len(part) / SR * FPS))])
    return np.concatenate(out) if out else np.zeros((0, 527), dtype=np.float32)


def pool(x: np.ndarray, per: int) -> np.ndarray:
    n = len(x) // per
    return x[:n * per].reshape(n, per, *x.shape[1:]).max(1) if n else x[:0]


def analyse(model, index, src: Path) -> dict:
    audio = read_audio(src)
    duration = len(audio) / SR
    per = int(STEP_S * SR)
    n = len(audio) // per
    frames = audio[:n * per].reshape(n, per) if n else np.zeros((0, per), dtype=np.float32)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-6)
    curves = {"db": [round(float(v), 1) for v in db]}
    if n:
        fw = framewise(model, audio)
        steps = pool(fw, int(STEP_S * FPS))[:n]
        for g, cols in index.items():
            curves[g] = [round(float(v), 3) for v in steps[:, cols].max(1)]
    return {"duration_s": round(duration, 2), "step_s": STEP_S, "curves": curves}


# ---------- detection (from the cache) ----------

def smooth(x: np.ndarray, n: int) -> np.ndarray:
    return np.convolve(x, np.ones(n) / n, mode="same") if len(x) >= n > 1 else x


def spans(mask: np.ndarray, step: float, min_s: float, gap_s: float) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(np.int8), [0]])))
    for a, b in zip(edges[::2], edges[1::2]):
        s, e = a * step, b * step
        if out and s - out[-1][1] <= gap_s:
            out[-1][1] = e
        else:
            out.append([s, e])
    return [(round(s, 2), round(e, 2)) for s, e in out if e - s >= min_s]


def speech_level(db: np.ndarray) -> float | None:
    loud = db[db > -55]
    return float(np.median(loud)) if len(loud) >= 8 else None


def excited_words(words: list[dict]) -> list[dict]:
    """Words that read as shouted or celebrating, with why."""
    out = []
    norm = [plain(re.sub(r"[^\w\s]", "", w["text"])) for w in words]
    for i, w in enumerate(words):
        t, p = w["text"].strip(), norm[i]
        why = None
        if re.search(r"([a-zA-ZÀ-ÿ])\1{2,}", t):
            why = "stretched"  # AAAAH, Uuuuu, gooool
        elif t.isupper() and (len(p) >= 5 or (len(p) >= 3 and t.endswith("!"))):
            why = "caps"  # shouted; short acronyms (CNPJ, SP) stay out
        elif (p and i >= 2 and p == norm[i - 1] == norm[i - 2] and len(p) > 1 and p not in CALM_REPEATS
              and any(words[j]["text"].strip().endswith("!") for j in range(i - 2, i + 1))):
            why = "chant"  # Ola! Ola! Ola! (but not "não, não, não" or a stutter)
        elif p in EXCITED_WORDS or (i and f"{norm[i - 1]} {p}" in EXCITED_WORDS):
            why = "word"
        if why:
            out.append({"start": w["start"], "end": w["end"], "text": t, "why": why,
                        "bang": t.endswith("!")})
    return out


def detect(data: dict, words: list[dict], project_level: float | None) -> list[dict]:
    c = {k: np.array(v, dtype=float) for k, v in data["curves"].items()}
    step = data["step_s"]
    n = len(c["db"])
    if not n:
        return []
    k = max(1, int(SMOOTH_S / step))
    seeds = []
    for g in SOUND_MOMENTS:
        if g not in c:
            continue
        prob = smooth(c[g], k)
        for s, e in spans(prob >= GROUPS[g]["threshold"], step, MIN_EVENT_S, MERGE_GAP_S):
            seg = prob[int(s / step):int(e / step)]
            seeds.append({"kind": g, "start": s, "end": e, "peak": float(seg.max())})
    # Loudness: compared with the clip's usual level and the project's, whichever is lower, so a short clip
    # that is loud from start to end (a crowd shouting) still counts
    db = smooth(c["db"], k)
    levels = [x for x in (speech_level(c["db"]), project_level) if x is not None]
    if levels:
        base = min(levels)
        for s, e in spans(db >= base + LOUD_RISE_DB, step, 1.0, 1.0):
            seg = db[int(s / step):int(e / step)]
            seeds.append({"kind": "loud", "start": s, "end": e, "peak": float(seg.max() - base)})
    exc = excited_words(words)
    for w in exc:
        seeds.append({"kind": "shout" if w["why"] in ("stretched", "caps", "chant") else "words",
                      "start": w["start"], "end": max(w["end"], w["start"] + 0.3), "peak": 1.0, "text": w["text"]})
    seeds.sort(key=lambda x: x["start"])
    groups: list[list[dict]] = []
    for s in seeds:
        if groups and s["start"] - max(x["end"] for x in groups[-1]) <= MERGE_GAP_S:
            groups[-1].append(s)
        else:
            groups.append([s])
    moments = []
    for g in groups:
        kinds = {x["kind"] for x in g}
        start, end = min(x["start"] for x in g), max(x["end"] for x in g)
        sound = max((min(1.0, x["peak"] / 0.4) * GROUPS[x["kind"]]["weight"] for x in g if x["kind"] in GROUPS),
                    default=0.0)
        loud = max((min(1.0, (x["peak"] - LOUD_RISE_DB) / 12 + 0.4) for x in g if x["kind"] == "loud"), default=0.0)
        shouts = sum(x["kind"] == "shout" for x in g)
        said = sum(x["kind"] == "words" for x in g)
        text = min(1.0, 0.35 * shouts + 0.15 * said)
        # a lone "obrigado" or a lone loud second is not a moment; agreement between signals is what counts
        families = sum([sound > 0, loud > 0, text > 0])
        score = max(sound * 0.8, loud * 0.6, text * 0.6) + 0.15 * (families - 1)
        if families == 1 and not (sound >= 0.5 or shouts >= 2):
            score *= 0.6
        score = round(min(1.0, score), 2)
        scene = sorted(gname for gname in ("crowd", "singing", "music") if gname in c and gname not in kinds
                       and c[gname][int(start / step):int(end / step) + 1].max(initial=0) >= GROUPS[gname]["threshold"])
        moments.append({"start": round(start, 2), "end": round(end, 2), "score": score,
                        "signals": sorted(kinds), "scene": scene,
                        "shouted": [x["text"] for x in g if x["kind"] in ("shout", "words")][:8]})
    return moments


def words_between(words: list[dict], a: float, b: float) -> str:
    return " ".join(w["text"].strip() for w in words if w["end"] > a and w["start"] < b)


# ---------- project ----------

def find_clips(target: Path) -> tuple[Path, list[dict]]:
    """(project, clips): follows context-extractor's inventory when there is one, for the recording order."""
    if target.is_file():
        project = target.parent.parent if target.parent.name.lower() in ("raw", "brutos") else target.parent
        return project, [{"clip": target.stem, "src": target, "file": target.name}]
    project = target
    inv = project / "edit" / "context" / "inventory.json"
    if inv.exists():
        out = [{"clip": c["clip"], "src": project / (c.get("proxy") or c["file"]), "file": c["file"],
                "recorded_at": c.get("recorded_at"), "block": c.get("block")}
               for c in json.loads(inv.read_text(encoding="utf-8"))["clips"]
               if "error" not in c and c.get("has_audio", True)]
        return project, out
    raw = raw_dir(project)
    found = sorted(p for p in (raw.rglob("*") if raw else project.iterdir())
                   if p.is_file() and p.suffix.lower() in MEDIA_EXTS and not p.name.startswith("."))
    out = []
    for p in found:
        proxy = next((p.with_suffix(x) for x in (".LRF", ".lrf") if p.with_suffix(x).exists()), None)
        out.append({"clip": p.stem, "src": proxy or p, "file": p.relative_to(project).as_posix()})
    if not out:
        sys.exit(f"no media in {raw or project}")
    return project, out


def cache_path(project: Path, clip: str) -> Path:
    return project / "edit" / "moments" / "clips" / f"{clip}.json"


def fingerprint(src: Path) -> list:
    st = src.stat()
    return [VERSION, st.st_size, st.st_mtime_ns]


def cached(project: Path, c: dict) -> dict | None:
    p = cache_path(project, c["clip"])
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return d if d.get("fingerprint") == fingerprint(c["src"]) else None


def report(project: Path, clips: list[dict], min_score: float) -> dict:
    data = {c["clip"]: d for c in clips if (d := cached(project, c))}
    levels = [x for d in data.values() if (x := speech_level(np.array(d["curves"]["db"]))) is not None]
    project_level = float(np.median(levels)) if levels else None
    rows = []
    for c in clips:
        d = data.get(c["clip"])
        if not d:
            continue
        tp = transcript_path(project / "edit", c["clip"])
        words = load_words(tp, only_words=True) if tp.exists() else []
        for m in detect(d, words, project_level):
            if m["score"] < min_score:
                continue
            rows.append({"clip": c["clip"], "file": c["file"], "block": c.get("block"),
                         "recorded_at": c.get("recorded_at"), **m,
                         "said_before": words_between(words, m["start"] - CONTEXT_BEFORE_S, m["start"]),
                         "said_during": words_between(words, m["start"], m["end"] + CONTEXT_AFTER_S),
                         "transcript": tp.exists()})
    rows.sort(key=lambda r: -r["score"])

    def cell(s: str, n: int = 180) -> str:
        s = re.sub(r"\s+", " ", s).replace("|", "/").strip()
        return ("…" + s[-n:] if len(s) > n else s) or "—"

    lines = [f"# Moments: {project.name}", "",
             f"{len(rows)} moments with score >= {min_score} in {len(data)} analysed clips, strongest first. "
             "Found in the sound itself and in how things were said, not in what was said. "
             "Times are seconds from the start of the clip. Generated by `moments.py`; do not edit.", "",
             "Signals: applause, cheering, laughter, crying, crowd (sound model); loud (well above the usual "
             "speaking level); shout (stretched, capitalised or chanted words in the transcript); words "
             "(celebration words).", "",
             "| # | clip | time | score | signals | said right before | said during |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        sig = ", ".join(r["signals"]) + (f" (over {', '.join(r['scene'])})" if r["scene"] else "")
        lines.append(f"| {i} | {r['clip']} | {r['start']:.1f}-{r['end']:.1f} ({clock(r['start'])}) | {r['score']:.2f} "
                     f"| {sig} | {cell(r['said_before'])} | {cell(r['said_during'])} |")
    out = project / "edit" / "moments" / "moments.md"
    write(out, "\n".join(lines) + "\n")
    write(out.with_suffix(".json"), json.dumps(rows, ensure_ascii=False, indent=1))
    by: dict[str, int] = {}
    for r in rows:
        for s in r["signals"]:
            by[s] = by.get(s, 0) + 1
    return {"project": str(project), "clips": len(clips), "analysed": len(data),
            "missing": [c["clip"] for c in clips if c["clip"] not in data],
            "without_transcript": sorted({r["clip"] for r in rows if not r["transcript"]}),
            "moments": len(rows), "by_signal": by, "report": str(out),
            "top": [{k: r[k] for k in ("clip", "start", "end", "score", "signals", "shouted")} for r in rows[:12]]}


def cmd_scan(args) -> None:
    project, clips = find_clips(args.target.resolve())
    todo = [c for c in clips if args.redo or not cached(project, c)]
    if todo:
        print("loading model...", flush=True)
        model, index = load_model()
        import torch
        torch.set_num_threads(max(1, torch.get_num_threads() // max(1, args.jobs)))
        t0, done = time.time(), [0]

        def one(c: dict) -> None:
            try:
                d = analyse(model, index, c["src"])
            except Exception as e:  # one unreadable file should not stop a long run
                print(f"{c['clip']}: failed: {e}", flush=True)
                return
            d.update({"clip": c["clip"], "file": c["file"], "source": c["src"].name,
                      "fingerprint": fingerprint(c["src"])})
            write(cache_path(project, c["clip"]), json.dumps(d, separators=(",", ":")))
            done[0] += 1
            print(f"[{done[0]}/{len(todo)}] {c['clip']} ({d['duration_s']:.0f}s)", flush=True)

        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
            list(ex.map(one, todo))
        print(f"analysed {done[0]} clip(s) in {time.time() - t0:.0f}s", flush=True)
    dump({**report(project, clips, args.min_score), "analysed_now": len(todo),
          "next": "read moments.md; check the strongest moments against the transcript and, for video, the frames; "
                  "then report them to the user or hand them to the skill that asked"})


def cmd_report(args) -> None:
    project, clips = find_clips(args.target.resolve())
    dump(report(project, clips, args.min_score))


def cmd_status(args) -> None:
    project, clips = find_clips(args.target.resolve())
    missing = [c["clip"] for c in clips if not cached(project, c)]
    dump({"project": str(project), "clips": len(clips), "analysed": len(clips) - len(missing), "missing": missing,
          "model_ready": MODEL.exists() and MODEL.stat().st_size >= MODEL_MIN_BYTES,
          "report": str(project / "edit" / "moments" / "moments.md")})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(fn=lambda a: dump(setup()))
    for name, fn in (("scan", cmd_scan), ("report", cmd_report), ("status", cmd_status)):
        p = sub.add_parser(name)
        p.add_argument("target", type=Path, help="project folder, or a single video/audio file")
        if name != "status":
            p.add_argument("--min-score", type=float, default=0.4)
        if name == "scan":
            p.add_argument("--jobs", type=int, default=2)
            p.add_argument("--redo", action="store_true", help="analyse again the clips already cached")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
