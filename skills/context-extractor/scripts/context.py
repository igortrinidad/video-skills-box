"""Per-clip context for a footage project: inventory, transcripts, contact sheets, worksheets, catalog.

Everything is written to <project>/edit/context/ and every step is cached per clip, so running
again after new footage arrives only processes the new clips.

    inventory.json     clips in recording order, grouped into days and blocks
    frames/<clip>.jpg  contact sheet (timestamped frames)
    work/<clip>.md     worksheet: metadata + phrase-level transcript (input for the insight writer)
    clips/<clip>.md    insight file, written by the agent
    knowledge.md       digest of the knowledge base (people, companies, terms), rewritten by `prepare`
    catalog.md         one line per clip, generated from the insight frontmatter

Transcripts go to <project>/edit/transcripts/<clip>.json, shared with the editing skills.

Usage:
    python context.py prepare <project> [--gap-min 10] [--utc-offset -3] [--language pt]
                                        [--engine mediacript] [--jobs 4] [--no-transcribe]
    python context.py status <project>
    python context.py labels <project> [--set "old label=New Name" ...] [--apply]
    python context.py catalog <project>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))

from videokit import knowledge  # noqa: E402
from videokit.cli import run_main  # noqa: E402
from videokit.media import VIDEO_EXTS, capture  # noqa: E402
from videokit.project import raw_dir  # noqa: E402
from videokit.transcribe import DEFAULT_ENGINE, ENGINES, transcribe_all  # noqa: E402
from videokit.transcript import DEFAULT_PROMPT, load_words, transcript_path  # noqa: E402

TYPES = ["talk", "to-camera", "interview", "conversation", "b-roll", "behind-the-scenes", "screen", "discard"]
VALUES = ["high", "medium", "low", "none"]
QUALITY = ["good", "fair", "poor"]
NAME_KEYS = ("people", "mentions")
PHRASE_GAP_S = 0.6
PHRASE_MAX_S = 12.0


def dump(obj) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def ctx_dir(project: Path) -> Path:
    return project / "edit" / "context"


def load_inventory(project: Path) -> dict:
    path = ctx_dir(project) / "inventory.json"
    if not path.exists():
        sys.exit(f"no inventory at {path}: run `context.py prepare` first")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- inventory ----------

def find_clips(project: Path) -> list[Path]:
    raw = raw_dir(project)
    found = raw.rglob("*") if raw else project.iterdir()
    clips = sorted(p for p in found if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not p.name.startswith("."))
    if not clips:
        sys.exit(f"no video files in {raw or project}")
    stems = [p.stem for p in clips]
    dupes = sorted({s for s in stems if stems.count(s) > 1})
    if dupes:
        sys.exit(f"clips with the same name in different folders (transcripts are keyed by name): {dupes}")
    return clips


def proxy_of(clip: Path) -> Path | None:
    """DJI low-res proxy recorded next to the original (same audio, ~6x smaller)."""
    for ext in (".LRF", ".lrf"):
        if clip.with_suffix(ext).exists():
            return clip.with_suffix(ext)
    return None


def recorded_at(clip: Path, created: str | None, duration: float, utc_offset: float | None) -> tuple[datetime, str]:
    if created:
        t = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if t.year > 2000:  # cameras with an unset clock write 1970/1904
            local = t.astimezone() if utc_offset is None else t + timedelta(hours=utc_offset)
            return local.replace(tzinfo=None, microsecond=0), "metadata"
    m = re.search(r"(20\d{12})", clip.name)
    if m:
        return datetime.strptime(m[1], "%Y%m%d%H%M%S"), "filename"
    return datetime.fromtimestamp(clip.stat().st_mtime) - timedelta(seconds=duration), "mtime"


def probe_clip(project: Path, clip: Path, utc_offset: float | None) -> dict:
    stat = clip.stat()
    proxy = proxy_of(clip)
    entry = {"clip": clip.stem, "file": clip.relative_to(project).as_posix(),
             "proxy": proxy.relative_to(project).as_posix() if proxy else None,
             "fingerprint": [stat.st_size, stat.st_mtime_ns]}
    r = capture(["ffprobe", "-v", "error", "-show_entries",
                 "stream=codec_type,width,height:stream_side_data=rotation:format=duration:format_tags=creation_time",
                 "-of", "json", str(clip)])
    try:
        d = json.loads(r.stdout)
        v = next(s for s in d["streams"] if s.get("codec_type") == "video")
        duration = float(d["format"]["duration"])
    except (ValueError, KeyError, StopIteration):
        return {**entry, "error": "unreadable (ffprobe found no video stream or duration)"}
    w, h = v["width"], v["height"]
    if any(abs(int(sd.get("rotation", 0))) in (90, 270) for sd in v.get("side_data_list", [])):
        w, h = h, w
    has_audio = any(s.get("codec_type") == "audio" for s in d["streams"])
    mean_db = max_db = None
    if has_audio:
        vol = capture(["ffmpeg", "-hide_banner", "-nostats", "-i", str(proxy or clip), "-vn",
                       "-af", "volumedetect", "-f", "null", "-"]).stderr
        mean_db, max_db = (float(m[1]) if (m := re.search(rf"{k}_volume: (-?[\d.]+) dB", vol)) else None
                           for k in ("mean", "max"))
    when, source = recorded_at(clip, d["format"].get("tags", {}).get("creation_time"), duration, utc_offset)
    return {**entry, "duration_s": round(duration, 2), "width": w, "height": h,
            "orientation": "vertical" if h > w else "horizontal", "has_audio": has_audio,
            "mean_db": mean_db, "max_db": max_db, "recorded_at": when.isoformat(), "time_source": source}


def assign_blocks(clips: list[dict], gap_min: float) -> None:
    """Days are distinct recording dates; a block is a run of clips with no gap longer than gap_min."""
    ok = sorted((c for c in clips if "error" not in c), key=lambda c: c["recorded_at"])
    dates = sorted({c["recorded_at"][:10] for c in ok})
    prev_end, day, block = None, None, 0
    for c in ok:
        start = datetime.fromisoformat(c["recorded_at"])
        d = dates.index(c["recorded_at"][:10]) + 1
        if d != day:
            day, block = d, 1
        elif (start - prev_end).total_seconds() > gap_min * 60:
            block += 1
        c["day"], c["block"] = f"D{day}", f"D{day}-B{block:02d}"
        prev_end = start + timedelta(seconds=c["duration_s"])


def scan(project: Path, gap_min: float, utc_offset: float | None, jobs: int) -> dict:
    path = ctx_dir(project) / "inventory.json"
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    # Recording times depend on the offset, so a different offset re-probes everything
    old = {c["clip"]: c for c in prev["clips"]} if prev and prev.get("utc_offset") == utc_offset else {}
    files = find_clips(project)

    def one(clip: Path) -> dict:
        cached = old.get(clip.stem)
        stat = clip.stat()
        proxy = proxy_of(clip)
        if cached and "error" not in cached and cached["fingerprint"] == [stat.st_size, stat.st_mtime_ns]:
            return {**cached, "file": clip.relative_to(project).as_posix(),
                    "proxy": proxy.relative_to(project).as_posix() if proxy else None}
        return probe_clip(project, clip, utc_offset)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        clips = list(pool.map(one, files))
    assign_blocks(clips, gap_min)
    clips.sort(key=lambda c: (c.get("recorded_at", "9999"), c["clip"]))
    inv = {"project": project.name, "gap_min": gap_min, "utc_offset": utc_offset, "clips": clips}
    write(path, json.dumps(inv, ensure_ascii=False, indent=1))
    return inv


# ---------- contact sheets ----------

def frame_times(duration: float) -> list[float]:
    n = max(3, min(20, round(duration / 8)))
    return [round(duration * (i + 0.5) / n, 2) for i in range(n)]


def clock(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def contact_sheet(project: Path, c: dict, out: Path) -> bool:
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.load_default(size=16)
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
    tile_w, cols = (216, 7) if c["orientation"] == "vertical" else (384, 4)
    src = project / (c["proxy"] or c["file"])
    tiles = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(frame_times(c["duration_s"])):
            f = Path(tmp) / f"{i:02d}.jpg"
            capture(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(src), "-map", "0:v:0", "-frames:v", "1",
                     "-vf", f"scale={tile_w}:-2", "-q:v", "4", str(f)])
            if f.exists():
                im = Image.open(f).convert("RGB")
                d = ImageDraw.Draw(im)
                label = clock(t)
                d.rectangle([0, 0, 12 + 9 * len(label), 22], fill=(0, 0, 0))
                d.text((5, 2), label, fill=(255, 255, 0), font=font)
                tiles.append(im)
    if not tiles:
        return False
    tw, th = tiles[0].size
    cols = min(cols, len(tiles))
    sheet = Image.new("RGB", (cols * tw, -(-len(tiles) // cols) * th), (30, 30, 30))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=85)
    return True


# ---------- worksheets ----------

def phrases(words: list[dict]) -> list[list[dict]]:
    """Break on silence, and at sentence ends once a phrase gets long, so ranges stay quotable."""
    out: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] >= PHRASE_GAP_S
                    or (cur[-1]["end"] - cur[0]["start"] >= PHRASE_MAX_S and cur[-1]["text"].rstrip()[-1:] in ".?!")):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def fmt_dur(s: float) -> str:
    return f"{s:.1f}s" if s < 60 else f"{int(s // 60)}m{int(s % 60):02d}s"


def worksheet(project: Path, c: dict, prev: dict | None, nxt: dict | None, position: str,
              entries: list[dict] | None = None) -> str:
    tp = transcript_path(project / "edit", c["clip"])
    words = load_words(tp, only_words=True) if tp.exists() else []
    lines = [f"[{p[0]['start']:06.2f}-{p[-1]['end']:06.2f}] " + " ".join(w["text"].strip() for w in p)
             for p in phrases(words)]
    heard = knowledge.spot(entries or [], " ".join(w["text"].strip() for w in words))
    known = "\n".join(f'- "{w}" → ' + (names[0] if len(names) == 1 else
                                       "one of: " + ", ".join(names) + " (decide from the context)")
                      for w, names in heard)
    known = f"""
## Names the knowledge base recognizes in this transcript

Write them as shown on the right. Any other name of a person or company in the transcript is new.

{known}
""" if heard else ""
    if not c["has_audio"]:
        speech = "_no audio track_"
    elif not tp.exists():
        speech = "_not transcribed yet_"
    else:
        speech = "\n".join(lines) or "_no speech detected_"
    level = f"mean {c['mean_db']} dB, peak {c['max_db']} dB" if c["mean_db"] is not None else "none"

    def neighbour(o: dict | None, label: str) -> str:
        if not o:
            return f"{label}: none in this block"
        a, b = (o, c) if label == "previous" else (c, o)
        gap = (datetime.fromisoformat(b["recorded_at"]) - datetime.fromisoformat(a["recorded_at"])).total_seconds()
        return f"{label}: {o['clip']} ({fmt_dur(max(0.0, gap - a['duration_s']))} gap)"

    stub = yaml.safe_dump({"clip": c["clip"], "file": c["file"], "recorded_at": c["recorded_at"][:16],
                           "block": c["block"], "duration_s": c["duration_s"], "orientation": c["orientation"]},
                          sort_keys=False, allow_unicode=True).strip()
    return f"""# Worksheet: {c['clip']}

- recorded: {c['recorded_at'].replace('T', ' ')} (time from {c['time_source']}), {c['block']}, clip {position}
- {neighbour(prev, 'previous')}; {neighbour(nxt, 'next')}
- duration: {fmt_dur(c['duration_s'])}, {c['orientation']} {c['width']}x{c['height']}
- audio: {level}; speech: {len(words)} words ({round(len(words) / (c['duration_s'] / 60))} per minute)
- contact sheet: ../frames/{c['clip']}.jpg (frames at {', '.join(clock(t) for t in frame_times(c['duration_s']))})

## Frontmatter to copy into ../clips/{c['clip']}.md

```yaml
{stub}
```
{known}
## Transcript (seconds from the start of the clip)

{speech}
"""


# ---------- insights ----------

def read_insight(path: Path) -> tuple[dict | None, list[str]]:
    text = path.read_text(encoding="utf-8-sig")
    m = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return None, ["no YAML frontmatter"]
    try:
        fm = yaml.safe_load(m[1])
    except yaml.YAMLError as e:
        return None, [f"frontmatter is not valid YAML: {str(e).splitlines()[0]}"]
    if not isinstance(fm, dict):
        return None, ["frontmatter is not a mapping"]
    problems = []
    if fm.get("clip") != path.stem:
        problems.append("`clip` does not match the file name")
    if fm.get("type") not in TYPES:
        problems.append(f"`type` must be one of {TYPES}")
    if fm.get("value") not in VALUES:
        problems.append(f"`value` must be one of {VALUES}")
    for key in ("audio", "image"):
        if fm.get(key) not in QUALITY:
            problems.append(f"`{key}` must be one of {QUALITY}")
    if not isinstance(fm.get("summary"), str) or not fm["summary"].strip():
        problems.append("`summary` is missing")
    for key in ("people", "mentions", "topics"):
        if not isinstance(fm.get(key) or [], list):
            problems.append(f"`{key}` must be a list")
    return fm, problems


def load_kb(project: Path) -> tuple[Path | None, list[dict]]:
    kb = knowledge.find_kb(project)
    return kb, (knowledge.load_entries(kb)[0] if kb else [])


def names_of(fm: dict | None, key: str) -> list[str]:
    v = (fm or {}).get(key)
    return [str(x) for x in v] if isinstance(v, list) else []


def collect_names(insights: dict[str, dict | None]) -> dict[str, dict[str, list[str]]]:
    """{field: {label: clips that use it}} for the fields that name people and companies."""
    used: dict[str, dict[str, list[str]]] = {k: {} for k in NAME_KEYS}
    for clip, fm in insights.items():
        for key in NAME_KEYS:
            for label in names_of(fm, key):
                used[key].setdefault(label, []).append(clip)
    return used


def label_report(used: dict[str, dict[str, list[str]]], entries: list[dict],
                 forced: dict[str, str] | None = None) -> dict:
    forced = forced or {}
    rename, unknown, inferred = [], [], []
    for key, labels in used.items():
        for label, where in labels.items():
            state, new = knowledge.label_status(entries, label)
            new = forced.get(label, new)
            row = {"label": label, "field": key, "clips": where}
            if new and new != label:
                rename.append({**row, "to": new})
            # `people` may hold a description of someone nobody named; `mentions` only holds names
            elif state == "unknown" or (state == "described" and key == "mentions"):
                unknown.append(row)
            if state == "inferred" and label not in forced:
                inferred.append(row)
    return {"rename": rename, "names_not_in_knowledge_base": unknown, "inferred": inferred}


def misspellings(ctx: Path, entries: list[dict]) -> list[dict]:
    """Spellings the knowledge base lists as wrong (`heard_as`) still written in the insight files or the timeline."""
    files = [*sorted((ctx / "clips").glob("*.md")), ctx / "timeline.md"]
    texts = {f.name: f.read_text(encoding="utf-8-sig") for f in files if f.exists()}
    out = []
    for e in entries:
        m = e["meta"]
        good = {str(m["name"]), *(str(a) for a in m.get("aliases") or [])}
        for h in m.get("heard_as") or []:
            rx = re.compile(rf"(?<!\w){re.escape(str(h))}(?!\w)", re.I)
            where = [name for name, text in texts.items() if any(x not in good for x in rx.findall(text))]
            if where:
                out.append({"written": str(h), "use": m["name"], "files": where})
    return out


def status(project: Path) -> dict:
    inv = load_inventory(project)
    ctx = ctx_dir(project)
    clips = [c for c in inv["clips"] if "error" not in c]
    known = {c["clip"] for c in clips}
    missing: dict[str, list[str]] = {}
    insights: dict[str, dict | None] = {}
    invalid, newest = [], 0.0
    for c in clips:
        f = ctx / "clips" / f"{c['clip']}.md"
        if not f.exists():
            missing.setdefault(c["block"], []).append(c["clip"])
            continue
        newest = max(newest, f.stat().st_mtime)
        insights[c["clip"]], problems = read_insight(f)
        if problems:
            invalid.append({"clip": c["clip"], "problems": problems})
    kb, entries = load_kb(project)
    catalog = ctx / "catalog.md"
    days: dict[str, dict] = {}
    for c in clips:
        d = days.setdefault(c["day"], {"date": c["recorded_at"][:10], "clips": 0, "minutes": 0.0, "blocks": set()})
        d["clips"] += 1
        d["minutes"] += c["duration_s"] / 60
        d["blocks"].add(c["block"])
    for d in days.values():
        d["minutes"], d["blocks"] = round(d["minutes"], 1), len(d["blocks"])
    return {
        "project": str(project), "context": str(ctx), "clips": len(clips), "days": days,
        "with_proxy": sum(bool(c["proxy"]) for c in clips),
        "unreadable": [{"file": c["file"], "error": c["error"]} for c in inv["clips"] if "error" in c],
        "transcripts_missing": [c["clip"] for c in clips if c["has_audio"]
                                and not transcript_path(project / "edit", c["clip"]).exists()],
        "frames_missing": [c["clip"] for c in clips if not (ctx / "frames" / f"{c['clip']}.jpg").exists()],
        "insights_done": len(clips) - sum(len(v) for v in missing.values()),
        "insights_missing": [{"block": b, "clips": v} for b, v in missing.items()],
        "insights_invalid": invalid,
        "insights_without_clip": sorted(p.stem for p in (ctx / "clips").glob("*.md") if p.stem not in known)
        if (ctx / "clips").is_dir() else [],
        "catalog": "missing" if not catalog.exists() else
                   "stale" if missing or invalid or catalog.stat().st_mtime < newest else "current",
        "knowledge": {"base": str(kb) if kb else None,
                      "digest": str(ctx / "knowledge.md") if (ctx / "knowledge.md").exists() else None,
                      "names": label_report(collect_names(insights), entries) if kb else None,
                      "misspellings": misspellings(ctx, entries) if kb else None},
    }


def cmd_labels(args) -> None:
    """Rewrite `people` and `mentions`: names the knowledge base knows under another spelling, plus --set pairs."""
    project = args.project.resolve()
    ctx = ctx_dir(project)
    forced = {}
    for pair in args.set:
        old, sep, new = pair.partition("=")
        if not sep or not old.strip() or not new.strip():
            sys.exit(f'--set expects "old label=New Name", got: {pair}')
        forced[old.strip()] = new.strip()
    _, entries = load_kb(project)
    insights: dict[str, dict | None] = {}
    for c in load_inventory(project)["clips"]:
        f = ctx / "clips" / f"{c['clip']}.md"
        if "error" not in c and f.exists():
            insights[c["clip"]] = read_insight(f)[0]
    used = collect_names(insights)
    report = label_report(used, entries, forced)
    unused = sorted(set(forced) - {label for labels in used.values() for label in labels})
    to = {r["label"]: r["to"] for r in report["rename"]}
    changed = []
    if args.apply:
        for clip, fm in insights.items():
            f = ctx / "clips" / f"{clip}.md"
            head, sep, body = f.read_text(encoding="utf-8-sig").partition("\n---")
            done = 0
            for key in NAME_KEYS:
                old = names_of(fm, key)
                new = list(dict.fromkeys(to.get(p, p) for p in old))
                if new == old:
                    continue
                line = f"{key}: " + yaml.safe_dump(new, default_flow_style=True, allow_unicode=True,
                                                   width=10 ** 9).strip()
                head, n = re.subn(rf"^{key}:.*(?:\n(?:[ \t]+|- ).*)*", lambda _: line, head, count=1, flags=re.M)
                done += n
            if done:
                write(f, head + sep + body)
                changed.append(clip)
    dump({**report, "set_labels_not_found": unused, "applied": args.apply, "files_changed": changed})


def cell(v) -> str:
    text = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v or "")
    return re.sub(r"\s+", " ", text).replace("|", "/").strip()


def cmd_catalog(args) -> None:
    project = args.project.resolve()
    st = status(project)
    if st["insights_missing"] or st["insights_invalid"]:
        dump({k: st[k] for k in ("insights_missing", "insights_invalid")})
        sys.exit("catalog not written: every clip needs a valid insight file first")
    inv = load_inventory(project)
    ctx = ctx_dir(project)
    rows = [(c, read_insight(ctx / "clips" / f"{c['clip']}.md")[0]) for c in inv["clips"] if "error" not in c]
    out = [f"# Catalog: {inv['project']}", "",
           f"{len(rows)} clips, {sum(c['duration_s'] for c, _ in rows) / 60:.0f} min. "
           "Generated by `context.py catalog` from `clips/*.md`; edit those files, not this one.", "",
           "| value | clips | minutes |", "|---|---|---|"]
    for v in VALUES:
        sel = [c for c, fm in rows if fm["value"] == v]
        out.append(f"| {v} | {len(sel)} | {sum(c['duration_s'] for c in sel) / 60:.1f} |")
    block = None
    for c, fm in rows:
        if c["block"] != block:
            block = c["block"]
            in_block = [x for x, _ in rows if x["block"] == block]
            out += ["", f"## {block} ({c['recorded_at'][:10]}, {in_block[0]['recorded_at'][11:16]} to "
                        f"{in_block[-1]['recorded_at'][11:16]}, {len(in_block)} clips)", "",
                    "| clip | time | length | frame | type | value | people | mentions | topics | summary |",
                    "|---|---|---|---|---|---|---|---|---|---|"]
        out.append("| " + " | ".join([c["clip"], c["recorded_at"][11:16], fmt_dur(c["duration_s"]),
                                      c["orientation"], fm["type"], fm["value"], cell(fm.get("people")),
                                      cell(fm.get("mentions")), cell(fm.get("topics")), cell(fm["summary"])]) + " |")
    write(ctx / "catalog.md", "\n".join(out) + "\n")
    dump({"catalog": str(ctx / "catalog.md"), "clips": len(rows)})


def cmd_prepare(args) -> None:
    project = args.project.resolve()
    if not project.is_dir():
        sys.exit(f"folder not found: {project}")
    ctx = ctx_dir(project)
    print("inventory...", flush=True)
    inv = scan(project, args.gap_min, args.utc_offset, args.jobs)
    clips = [c for c in inv["clips"] if "error" not in c]

    kb, entries = load_kb(project)
    names = knowledge.prompt_terms(entries, knowledge.terms(kb)) if kb else ""
    if kb:
        write(ctx / "knowledge.md", knowledge.digest(kb, with_profile=False))

    if not args.no_transcribe:
        todo = [project / c["file"] for c in clips if c["has_audio"]
                and not transcript_path(project / "edit", c["clip"]).exists()]
        if todo:
            print(f"transcribing {len(todo)} clip(s)...", flush=True)
            # Names in the prompt bias the recognizer towards the right spelling
            failed = transcribe_all(todo, project / "edit", args.language or None,
                                    prompt=f"{DEFAULT_PROMPT} {names}." if names else DEFAULT_PROMPT,
                                    engine=args.engine)
            if failed:
                print(f"transcription failed for {len(failed)} clip(s); they stay in transcripts_missing "
                      "until prepare runs again", flush=True)

    todo = [c for c in clips if not (ctx / "frames" / f"{c['clip']}.jpg").exists()]
    if todo:
        print(f"contact sheets for {len(todo)} clip(s)...", flush=True)
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            list(pool.map(lambda c: contact_sheet(project, c, ctx / "frames" / f"{c['clip']}.jpg"), todo))

    # Always rewritten: cheap, and a clip's neighbours change when more footage arrives
    by_block: dict[str, list[dict]] = {}
    for c in clips:
        by_block.setdefault(c["block"], []).append(c)
    for group in by_block.values():
        for i, c in enumerate(group):
            write(ctx / "work" / f"{c['clip']}.md",
                  worksheet(project, c, group[i - 1] if i else None, group[i + 1] if i + 1 < len(group) else None,
                            f"{i + 1} of {len(group)} in the block", entries))
    dump(status(project))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("project", type=Path)
    p.add_argument("--gap-min", type=float, default=10, help="pause between clips that starts a new block")
    p.add_argument("--utc-offset", type=float, default=None,
                   help="hours from UTC where the footage was shot (default: this computer's time zone)")
    p.add_argument("--language", default="pt")
    p.add_argument("--engine", choices=ENGINES, default=DEFAULT_ENGINE,
                   help="mediacript (default): cloud only, a clip that fails stays untranscribed; "
                        "auto and whisper use the slow local Whisper")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--no-transcribe", action="store_true")
    p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("status"); p.add_argument("project", type=Path)
    p.set_defaults(fn=lambda a: dump(status(a.project.resolve())))
    p = sub.add_parser("labels"); p.add_argument("project", type=Path)
    p.add_argument("--set", action="append", default=[], metavar="OLD=NEW",
                   help="rename one label exactly as written in the insight files (repeatable)")
    p.add_argument("--apply", action="store_true", help="write the changes (default: only list them)")
    p.set_defaults(fn=cmd_labels)
    p = sub.add_parser("catalog"); p.add_argument("project", type=Path); p.set_defaults(fn=cmd_catalog)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    run_main(main)
