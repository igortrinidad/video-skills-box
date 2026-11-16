"""Plans videos from the context a footage project already has (context-extractor) and tracks them.

Everything is written to <project>/edit/explore/:

    session.json        what the user asked for (styles, formats, quantity, profile) and the batches
    material/<batch>.md the insight files of one batch of clips, joined (generated)
    notes/<batch>.md    what a scout found in that batch (written by the agent)
    videos/<ID>-<slug>.md   one file per video: plan + status in the frontmatter
    overview.md         every video by status (generated)

Usage:
    python explore.py status <project>
    python explore.py start <project> --style fun --style technical --format short [--format long]
                            [--shorts N] [--longs N] [--profile <name>] [--references <folder>] [--notes "..."] [--update]
    python explore.py material <project>            # rebuild the batches after new footage
    python explore.py new <project> --title "..." --format short --style fun [--duration 40] [--score 8]
    python explore.py check <project>               # validate notes and videos, rewrite overview.md
    python explore.py set <project> <ID> [<ID> ...] --status approved [--first] [--workdir D] [--final F] [--note "..."]
    python explore.py reset <project> [--all] [--yes]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))
from videokit import knowledge  # noqa: E402
from videokit.project import norm, reference_dirs  # noqa: E402

STYLES = ["fun", "technical", "vlog", "provocative", "story", "interview", "authority", "reaction", "promo", "recap"]
STYLE_ALIASES = {
    "divertido": "fun", "engracado": "fun", "zueira": "fun", "humor": "fun",
    "tecnico": "technical", "tutorial": "technical", "dica": "technical",
    "bastidores": "vlog", "provocativo": "provocative", "opiniao": "provocative", "polemico": "provocative",
    "historia": "story", "storytelling": "story", "entrevista": "interview", "conversa": "interview",
    "autoridade": "authority", "insight": "authority", "reacao": "reaction", "resposta": "reaction",
    "promocional": "promo", "venda": "promo", "resumo": "recap", "melhores momentos": "recap",
}
FORMATS = ["short", "long"]
STATUSES = ["proposed", "approved", "producing", "review", "delivered", "published", "rejected"]
NEEDS_APPROVAL = ("producing", "review", "delivered", "published")
BATCH_CHARS = 40_000
BATCH_CLIPS = 12
SEGMENT = re.compile(r"\[([\w.-]+)\s+(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\]")

VIDEO_BODY = """
## Idea
What the video is, in two or three sentences, and why this audience would watch it to the end.

## Hook
The first two seconds: the literal line or the image, and the text on screen.

## Structure
1. [<ref> 000.00-000.00] "literal words" - what this piece does in the video

## On screen
Title plates, information plates, subtitles, inserts.

## Publishing
Title options, caption idea, call to action.

## Risks
What has to be confirmed or avoided before publishing (people, numbers, permissions).

## Log
"""


def dump(obj) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def exp_dir(project: Path) -> Path:
    return project / "edit" / "explore"


def load_session(project: Path) -> dict | None:
    path = exp_dir(project) / "session.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_session(project: Path, session: dict) -> None:
    write(exp_dir(project) / "session.json", json.dumps(session, ensure_ascii=False, indent=1))


def fmt_dur(s: float) -> str:
    return f"{s:.0f}s" if s < 60 else f"{int(s // 60)}m{int(s % 60):02d}s"


# ---------- footage context ----------

def load_clips(project: Path) -> tuple[list[dict], list[str]]:
    """(clips that have a valid insight file, clips that lack one). Each clip carries `fm`, `text` and `ref`."""
    ctx = project / "edit" / "context"
    inv = ctx / "inventory.json"
    if not inv.exists():
        return [], []
    clips, missing = [], []
    for c in json.loads(inv.read_text(encoding="utf-8"))["clips"]:
        if "error" in c:
            continue
        f = ctx / "clips" / f"{c['clip']}.md"
        fm, body, err = knowledge.split_frontmatter(f.read_text(encoding="utf-8-sig")) if f.exists() else (None, "", "x")
        if err or not fm:
            missing.append(c["clip"])
            continue
        clips.append({**c, "fm": fm, "text": body.strip()})
    # Short reference for plans: the last run of digits when no other clip has the same ("0324" of DJI_..._0324_D)
    shorts = [(re.findall(r"\d{3,}", c["clip"]) or [c["clip"]])[-1] for c in clips]
    for c, short in zip(clips, shorts):
        c["ref"] = short if shorts.count(short) == 1 else c["clip"]
    return clips, missing


def resolve_ref(clips: list[dict], ref: str) -> dict | None:
    hits = [c for c in clips if ref in (c["clip"], c["ref"])]
    return hits[0] if len(hits) == 1 else None


def make_batches(clips: list[dict]) -> dict[str, list[dict]]:
    """Reading units for the scouts, named D1-01, D1-02...: a long block is split into even parts and short
    neighbouring blocks of the same day are joined, so every batch fits one reader. Discards are left out."""
    def size(part: list[dict]) -> int:
        return sum(len(c["text"]) for c in part)

    by_block: dict[str, list[dict]] = {}
    for c in clips:
        if c["fm"].get("type") != "discard":
            by_block.setdefault(c["block"], []).append(c)
    units: list[list[dict]] = []
    for group in by_block.values():
        n = max(-(-len(group) // BATCH_CLIPS), -(-size(group) // BATCH_CHARS), 1)
        parts: list[list[dict]] = [[] for _ in range(n)]
        done = 0
        for c in group:
            parts[min(n - 1, done * n // max(1, size(group)))].append(c)
            done += len(c["text"])
        units += [p for p in parts if p]
    out: dict[str, list[dict]] = {}
    current: list[dict] = []
    count: dict[str, int] = {}

    def close() -> None:
        if current:
            day = current[0]["day"]
            count[day] = count.get(day, 0) + 1
            out[f"{day}-{count[day]:02d}"] = list(current)
            current.clear()

    for unit in units:
        if current and (unit[0]["day"] != current[0]["day"] or len(current) + len(unit) > BATCH_CLIPS
                        or size(current) + size(unit) > BATCH_CHARS):
            close()
        current.extend(unit)
    close()
    return out


def batch_key(part: list[dict]) -> str:
    """Changes when the batch gets other clips or an insight file is rewritten, which makes its notes stale."""
    return "m" + hashlib.sha1("|".join(c["clip"] + c["text"] for c in part).encode()).hexdigest()[:8]


def write_material(project: Path, session: dict) -> dict:
    clips, _ = load_clips(project)
    folder = exp_dir(project) / "material"
    batches = make_batches(clips)
    for old in folder.glob("*.md") if folder.is_dir() else []:
        if old.stem not in batches:
            old.unlink()
    for bid, part in batches.items():
        key = batch_key(part)
        out = [f"# Material: batch {bid}", "",
               f"{len(part)} clips, {fmt_dur(sum(c['duration_s'] for c in part))}, recorded "
               f"{part[0]['recorded_at'][:16].replace('T', ' ')} to {part[-1]['recorded_at'][11:16]}. "
               "Generated by `explore.py`; the source is `edit/context/clips/`.", "",
               "Frontmatter for the notes file of this batch:", "", "```yaml",
               f"batch: {bid}", f"material: {key}", "```", ""]
        for c in part:
            fm = c["fm"]
            out += [f"## {c['ref']} = {c['clip']}", "",
                    f"{c['block']}, {c['recorded_at'][11:16]}, {fmt_dur(c['duration_s'])} ({c['duration_s']}s), "
                    f"{c['orientation']}, "
                    f"{fm.get('type')}, value {fm.get('value')}, audio {fm.get('audio')}, image {fm.get('image')}",
                    f"People: {', '.join(map(str, fm.get('people') or [])) or '-'}",
                    f"Mentions: {', '.join(map(str, fm.get('mentions') or [])) or '-'}",
                    f"Summary: {fm.get('summary')}", "",
                    re.sub(r"^## ", "### ", c["text"], flags=re.M), ""]
        write(folder / f"{bid}.md", "\n".join(out))
    session["batches"] = {bid: {"key": batch_key(part), "clips": [c["clip"] for c in part]}
                          for bid, part in batches.items()}
    return session["batches"]


# ---------- videos ----------

def load_videos(project: Path) -> list[dict]:
    out = []
    folder = exp_dir(project) / "videos"
    for f in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        fm, body, err = knowledge.split_frontmatter(f.read_text(encoding="utf-8-sig"))
        out.append({"file": f, "fm": fm or {}, "body": body, "error": err})
    return out


def save_video(v: dict) -> None:
    front = yaml.safe_dump(v["fm"], sort_keys=False, allow_unicode=True, width=10 ** 9)
    write(v["file"], f"---\n{front}---\n{v['body'] if v['body'].startswith(chr(10)) else chr(10) + v['body']}")


def segments(v: dict, clips: list[dict]) -> tuple[list[dict], list[str]]:
    """Footage ranges under `## Structure`: ([{clip, start, end}], problems)."""
    m = re.search(r"^## Structure\s*\n(.*?)(?=^## |\Z)", v["body"], re.S | re.M)
    segs, problems = [], []
    for ref, a, b in SEGMENT.findall(m[1] if m else ""):
        c = resolve_ref(clips, ref)
        start, end = float(a), float(b)
        if not c:
            problems.append(f"[{ref} {a}-{b}]: no clip (or more than one) matches `{ref}`")
        elif not 0 <= start < end <= c["duration_s"] + 0.5:
            problems.append(f"[{ref} {a}-{b}]: range outside the clip ({c['duration_s']}s)")
        else:
            segs.append({"clip": c["clip"], "start": start, "end": end})
    if not segs and not problems:
        problems.append("`## Structure` has no footage range like [0324 000.00-005.50]")
    return segs, problems


def check_video(v: dict, clips: list[dict], entries: list[dict]) -> dict:
    fm, problems, warnings = v["fm"], [], []
    if v["error"]:
        return {"problems": [v["error"]], "warnings": [], "segments": []}
    if not re.fullmatch(r"V\d{2,}", str(fm.get("id"))) or not v["file"].name.startswith(f"{fm.get('id')}-"):
        problems.append("`id` must be like V07 and start the file name")
    if not isinstance(fm.get("title"), str) or not fm["title"].strip():
        problems.append("`title` is missing")
    if fm.get("format") not in FORMATS:
        problems.append(f"`format` must be one of {FORMATS}")
    if fm.get("status") not in STATUSES:
        problems.append(f"`status` must be one of {STATUSES}")
    styles = fm.get("styles")
    if not isinstance(styles, list) or not styles:
        problems.append("`styles` must be a list with at least one style")
    else:
        warnings += [f"style `{s}` is not in the catalogue {STYLES}" for s in styles if s not in STYLES]
    segs, seg_problems = segments(v, clips)
    problems += seg_problems
    planned = sum(s["end"] - s["start"] for s in segs)
    target = fm.get("duration_s")
    if isinstance(target, (int, float)) and segs and not 0.6 * target <= planned <= 2.5 * target:
        warnings.append(f"ranges add up to {planned:.0f}s of footage for a {target}s video")
    for name in fm.get("people") or []:
        e, _ = knowledge.resolve(entries, str(name))
        publish = e["meta"].get("publish", "ok") if e else "ok"
        if publish == "avoid":
            problems.append(f"{name}: marked `publish: avoid` in the knowledge base")
        elif publish == "ask":
            warnings.append(f"{name}: ask the user before publishing (`publish: ask`)")
    template = {s.strip() for s in VIDEO_BODY.splitlines() if s.strip() and not s.startswith("## ")}
    left = [s.strip() for s in v["body"].splitlines() if s.strip() in template]
    if left:
        problems.append(f"the body still has template text to replace: \"{left[0][:60]}...\"")
    for title in re.findall(r"^## (.+?)\s*$", VIDEO_BODY, re.M):
        if title != "Log" and not re.search(rf"^## {title}\s*\n+(?!## )\S", v["body"], re.M):
            problems.append(f"section `## {title}` is missing or empty")
    return {"problems": problems, "warnings": warnings, "segments": segs}


def write_overview(project: Path, videos: list[dict], clips: list[dict], entries: list[dict]) -> None:
    refs = {c["clip"]: c["ref"] for c in clips}
    out = [f"# Videos: {project.name}", "",
           "Generated by `explore.py` from `videos/*.md`; edit those files (or use `explore.py set`), not this one.", ""]
    for status in STATUSES:
        rows = sorted((v for v in videos if v["fm"].get("status") == status),
                      key=lambda v: (v["fm"].get("priority") or 999, -(v["fm"].get("score") or 0), str(v["fm"].get("id"))))
        if not rows:
            continue
        out += [f"## {status} ({len(rows)})", "", "| id | title | format | styles | target | footage | clips | score |",
                "|---|---|---|---|---|---|---|---|"]
        for v in rows:
            fm = v["fm"]
            segs = check_video(v, clips, entries)["segments"]
            used = ", ".join(dict.fromkeys(refs.get(s["clip"], s["clip"]) for s in segs))
            out.append("| " + " | ".join([
                str(fm.get("id")), str(fm.get("title") or "").replace("|", "/"), str(fm.get("format")),
                ", ".join(map(str, fm.get("styles") or [])),
                fmt_dur(fm["duration_s"]) if isinstance(fm.get("duration_s"), (int, float)) else "",
                fmt_dur(sum(s["end"] - s["start"] for s in segs)) if segs else "", used,
                str(fm.get("score") or "")]) + " |")
        out.append("")
    write(exp_dir(project) / "overview.md", "\n".join(out))


# ---------- state ----------

def load_kb(project: Path, session: dict | None) -> tuple[Path | None, list[dict], dict | None, list[str]]:
    kb = knowledge.find_kb(project)
    entries = knowledge.load_entries(kb)[0] if kb else []
    profile, names = knowledge.pick_profile(entries, (session or {}).get("profile"))
    return kb, entries, profile, names


def write_digest(project: Path, session: dict) -> None:
    kb = knowledge.find_kb(project)
    if kb:
        write(exp_dir(project) / "knowledge.md", knowledge.digest(kb, session.get("profile")))


def notes_state(project: Path, bid: str, key: str) -> str:
    f = exp_dir(project) / "notes" / f"{bid}.md"
    if not f.exists():
        return "missing"
    fm, _, _ = knowledge.split_frontmatter(f.read_text(encoding="utf-8-sig"))
    return "done" if fm and str(fm.get("material")) == key else "stale"


def status(project: Path) -> dict:
    exp = exp_dir(project)
    session = load_session(project)
    clips, missing = load_clips(project)
    kb, entries, profile, profiles = load_kb(project, session)
    refs = [str(p) for p in reference_dirs(project)]
    batches = make_batches(clips)
    saved = (session or {}).get("batches", {})
    rows = [{"batch": bid, "clips": len(part), "minutes": round(sum(c["duration_s"] for c in part) / 60, 1),
             "material": str(exp / "material" / f"{bid}.md"),
             "notes": notes_state(project, bid, batch_key(part))} for bid, part in batches.items()]
    material_stale = bool(session) and {b: batch_key(p) for b, p in batches.items()} != {b: v["key"] for b, v in saved.items()}
    videos = load_videos(project)
    checks = {str(v["fm"].get("id") or v["file"].stem): check_video(v, clips, entries) for v in videos}
    by_status = {s: [str(v["fm"].get("id")) for v in videos if v["fm"].get("status") == s] for s in STATUSES}
    by_status = {s: ids for s, ids in by_status.items() if ids}

    if not clips or missing:
        nxt = "context: run the context-extractor skill on this project first (clips without an insight file)"
    elif not session:
        nxt = "ask: ask the opening questions, then run `start`"
    elif material_stale:
        nxt = "material: the footage context changed; run `material`, then scout the batches whose notes are missing or stale"
    elif any(r["notes"] != "done" for r in rows):
        nxt = "scout: write the notes of the batches whose notes are missing or stale"
    elif not videos:
        nxt = "plan: turn the notes into video plans with `new`, one video per step (create it, fill its file, then the next)"
    elif any(c["problems"] for c in checks.values()):
        nxt = ("fix: run `check` and fix the video files it reports, one file per step; a file with template text "
               "was created and not filled, so fill it and then continue planning the remaining videos")
    elif by_status.get("producing"):
        nxt = f"produce: resume {by_status['producing']} (read each video's `workdir`)"
    elif by_status.get("approved"):
        nxt = f"produce: {by_status['approved']} are approved; start with the lowest `priority`"
    elif by_status.get("review"):
        nxt = f"review: {by_status['review']} wait for the user's opinion"
    elif by_status.get("proposed"):
        nxt = "approve: present the proposed videos and wait for the user to choose"
    else:
        nxt = "done: nothing pending; ask the user whether to explore for more ideas"
    return {
        "project": str(project), "explore": str(exp),
        "context": {"clips": len(clips), "clips_without_insight": missing,
                    "timeline": str(project / "edit" / "context" / "timeline.md")
                    if (project / "edit" / "context" / "timeline.md").exists() else None},
        "knowledge": {"base": str(kb) if kb else None, "digest": str(exp / "knowledge.md") if (exp / "knowledge.md").exists() else None,
                      "profile": {"name": profile["meta"]["name"], "status": profile["meta"].get("status", "confirmed"),
                                  "file": profile["file"]} if profile else None,
                      "profiles": profiles},
        "references": {"chosen": (session or {}).get("references"), "found": refs},
        "session": {k: v for k, v in session.items() if k != "batches"} if session else None,
        "batches": rows,
        "videos": {"by_status": by_status,
                   "list": [{"id": v["fm"].get("id"), "title": v["fm"].get("title"), "format": v["fm"].get("format"),
                             "status": v["fm"].get("status"), "priority": v["fm"].get("priority"),
                             "file": str(v["file"])} for v in videos],
                   "problems": {k: c["problems"] for k, c in checks.items() if c["problems"]}},
        "next": nxt,
    }


# ---------- commands ----------

def style_of(s: str) -> str:
    return STYLE_ALIASES.get(norm(s), norm(s).replace(" ", "-"))


def cmd_start(args) -> None:
    project = args.project.resolve()
    clips, missing = load_clips(project)
    if not clips or missing:
        sys.exit(f"the footage context is incomplete ({len(missing)} clips without an insight file): "
                 "run the context-extractor skill first")
    session = load_session(project)
    if session and not args.update:
        sys.exit("this project already has an exploration: `status` shows it, `start --update` changes the answers, "
                 "`reset` starts over")
    session = session or {"created": datetime.now().isoformat(timespec="minutes")}
    if args.style:
        session["styles"] = list(dict.fromkeys(style_of(s) for s in args.style))
    if args.format:
        session["formats"] = list(dict.fromkeys(args.format))
    if not session.get("styles") or not session.get("formats"):
        sys.exit("--style and --format are required (ask the user; do not choose for them)")
    for key in ("shorts", "longs", "profile", "references", "notes"):
        if getattr(args, key) is not None:
            session[key] = getattr(args, key) or None
        session.setdefault(key, None)
    _, _, profile, profiles = load_kb(project, session)
    if session["profile"] and not profile:
        sys.exit(f"profile not found: {session['profile']} (profiles: {profiles})")
    if not session["references"]:
        found = reference_dirs(project)
        session["references"] = str(found[0]) if len(found) == 1 else None
    session["updated"] = datetime.now().isoformat(timespec="minutes")
    write_material(project, session)
    save_session(project, session)
    write_digest(project, session)
    for sub in ("notes", "videos"):
        (exp_dir(project) / sub).mkdir(parents=True, exist_ok=True)
    dump(status(project))


def cmd_material(args) -> None:
    project = args.project.resolve()
    session = load_session(project)
    if not session:
        sys.exit("no exploration yet: run `start` first")
    write_material(project, session)
    save_session(project, session)
    write_digest(project, session)
    dump(status(project))


def cmd_new(args) -> None:
    project = args.project.resolve()
    session = load_session(project)
    if not session:
        sys.exit("no exploration yet: run `start` first")
    videos = load_videos(project)
    title = args.title.strip()
    if any(norm(str(v["fm"].get("title"))) == norm(title) for v in videos):
        sys.exit(f"a video with this title already exists: {title}")
    numbers = [int(m[1]) for v in videos if (m := re.match(r"V(\d+)", v["file"].name))]
    vid = f"V{max(numbers, default=0) + 1:02d}"
    slug = re.sub(r"[^a-z0-9]+", "-", norm(title)).strip("-")[:50].strip("-") or "video"
    _, _, profile, _ = load_kb(project, session)
    fm = {"id": vid, "title": title, "format": args.format, "styles": [style_of(s) for s in args.style],
          "status": "proposed", "priority": None, "score": args.score, "duration_s": args.duration,
          "profile": profile["meta"]["name"] if profile else None, "people": args.person,
          "created": date.today(), "updated": date.today(), "workdir": None, "final": None}
    v = {"file": exp_dir(project) / "videos" / f"{vid}-{slug}.md", "fm": fm, "body": VIDEO_BODY}
    save_video(v)
    dump({"id": vid, "file": str(v["file"]),
          "next": "fill this file now with your file-editing tool (replace every section of the body with the real plan) "
                  "before creating the next video; one video per step, never several plans in one command or script; "
                  "run `check` after the last one"})


def cmd_check(args) -> None:
    project = args.project.resolve()
    clips, _ = load_clips(project)
    _, entries, _, _ = load_kb(project, load_session(project))
    videos = load_videos(project)
    report, use = [], {}
    for v in videos:
        c = check_video(v, clips, entries)
        if v["fm"].get("status") != "rejected":
            for s in c["segments"]:
                use.setdefault(s["clip"], set()).add(str(v["fm"].get("id")))
        if c["problems"] or c["warnings"]:
            report.append({"id": v["fm"].get("id"), "file": str(v["file"]),
                           "problems": c["problems"], "warnings": c["warnings"]})
    write_overview(project, videos, clips, entries)
    st = status(project)
    dump({"videos": len(videos), "by_status": st["videos"]["by_status"], "to_fix": report,
          "notes_not_done": [r["batch"] for r in st["batches"] if r["notes"] != "done"],
          "high_value_clips_in_no_video": [c["ref"] for c in clips if c["fm"].get("value") == "high" and c["clip"] not in use],
          "clips_in_several_videos": {next(c["ref"] for c in clips if c["clip"] == k): sorted(v)
                                      for k, v in use.items() if len(v) > 1},
          "overview": str(exp_dir(project) / "overview.md"), "next": st["next"]})


def log_line(v: dict, text: str) -> None:
    line = f"- {datetime.now():%Y-%m-%d %H:%M} {text}"
    body = v["body"].rstrip("\n")
    v["body"] = (body + "\n" + line + "\n") if re.search(r"^## Log\s*$", body, re.M) else f"{body}\n\n## Log\n{line}\n"


def cmd_set(args) -> None:
    project = args.project.resolve()
    videos = load_videos(project)
    by_id = {str(v["fm"].get("id")): v for v in videos}
    unknown = [i for i in args.ids if i not in by_id]
    if unknown:
        sys.exit(f"no video with id {unknown}; existing: {sorted(by_id)}")
    chosen = [by_id[i] for i in args.ids]
    if args.status in NEEDS_APPROVAL:
        early = [v["fm"]["id"] for v in chosen if v["fm"].get("status") in ("proposed", "rejected")]
        if early:
            sys.exit(f"{early} were not approved by the user: nothing is produced before approval "
                     f"(`set <ID> --status approved` only after the user says so)")
    if args.status == "approved":
        clips, _ = load_clips(project)
        _, entries, _, _ = load_kb(project, load_session(project))
        broken = {v["fm"]["id"]: p for v in chosen if (p := check_video(v, clips, entries)["problems"])}
        if broken:
            dump({"not_changed": broken})
            sys.exit("these plans have problems: fix the files, run `check`, then approve")
    for v in chosen:
        fm = v["fm"]
        changes = []
        if args.status and args.status != fm.get("status"):
            changes.append(f"{fm.get('status')} -> {args.status}")
            fm["status"] = args.status
        for key in ("workdir", "final"):
            if getattr(args, key):
                fm[key] = getattr(args, key)
                changes.append(f"{key}: {fm[key]}")
        if changes or args.note:
            log_line(v, "; ".join(changes) + (f" ({args.note})" if args.note and changes else args.note or ""))
        fm["updated"] = date.today()
    # One production order for everything approved or in production; the rest has no priority.
    # Newly approved videos go to the end in the order the user gave them, or to the front with --first.
    active = [v for v in videos if v["fm"].get("status") in ("approved", "producing")]
    picked = [v for v in chosen if v in active and (args.first or not v["fm"].get("priority"))]
    rest = sorted((v for v in active if v not in picked), key=lambda v: (v["fm"].get("priority") or 999, str(v["fm"]["id"])))
    queue = picked + rest if args.first else rest + picked
    for v in videos:
        priority = queue.index(v) + 1 if v in queue else None
        if v in chosen or priority != v["fm"].get("priority"):
            v["fm"]["priority"] = priority
            save_video(v)
    clips, _ = load_clips(project)
    _, entries, _, _ = load_kb(project, load_session(project))
    videos = load_videos(project)
    write_overview(project, videos, clips, entries)
    dump({"changed": [{"id": v["fm"]["id"], "status": v["fm"]["status"], "priority": v["fm"]["priority"],
                       "file": str(v["file"])} for v in load_videos(project) if str(v["fm"].get("id")) in args.ids],
          "production_order": [v["fm"]["id"] for v in queue], "next": status(project)["next"]})


def cmd_reset(args) -> None:
    project = args.project.resolve()
    exp = exp_dir(project)
    if not exp.is_dir():
        sys.exit("nothing to reset: this project has no exploration")
    videos = load_videos(project)
    kept = [] if args.all else [v for v in videos if v["fm"].get("status") not in ("proposed", "rejected")]
    targets = list(exp.iterdir()) if args.all else [
        *[p for p in (exp / "notes", exp / "material", exp / "overview.md", exp / "knowledge.md") if p.exists()],
        *[v["file"] for v in videos if v not in kept]]
    notes = len(list((exp / "notes").glob("*.md"))) if (exp / "notes").is_dir() else 0
    summary = {"would_remove": {"scout_notes": notes, "video_plans": len(videos) - len(kept),
                                "answers_to_the_opening_questions": bool(args.all)},
               "kept": {"video_plans": [f"{v['fm'].get('id')} ({v['fm'].get('status')})" for v in kept],
                        "answers_to_the_opening_questions": not args.all,
                        "always": "footage context (edit/context), production folders and final/"}}
    if not args.yes:
        dump({**summary, "done": False,
              "next": "tell the user exactly what would be removed and what is kept; run again with --yes only after they confirm"})
        return
    archive = project / "edit" / "explore-old" / f"{datetime.now():%Y%m%d-%H%M%S}"
    archive.mkdir(parents=True)
    for p in targets:
        dest = archive / p.relative_to(exp)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dest))
    if not args.all:
        session = load_session(project)
        if session:
            session["batches"] = {}
            save_session(project, session)
    dump({**summary, "done": True, "archived_in": str(archive), "next": status(project)["next"]})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name: str, fn):
        p = sub.add_parser(name)
        p.add_argument("project", type=Path)
        p.set_defaults(fn=fn)
        return p

    add("status", lambda a: dump(status(a.project.resolve())))
    p = add("start", cmd_start)
    p.add_argument("--style", action="append", default=[], help=f"repeatable: {', '.join(STYLES)} (or a new one)")
    p.add_argument("--format", action="append", default=[], choices=FORMATS, help="repeatable")
    p.add_argument("--shorts", type=int, help="how many shorts the user wants (omit: as many as are worth making)")
    p.add_argument("--longs", type=int, help="how many long videos the user wants (omit: as many as are worth making)")
    p.add_argument("--profile", help="profile of the knowledge base this content is for")
    p.add_argument("--references", help="folder with the production references (graphics, sounds, reference videos)")
    p.add_argument("--notes", help="anything else the user asked for, in their words")
    p.add_argument("--update", action="store_true", help="change the answers of an exploration that already exists")
    add("material", cmd_material)
    p = add("new", cmd_new)
    p.add_argument("--title", required=True)
    p.add_argument("--format", required=True, choices=FORMATS)
    p.add_argument("--style", action="append", required=True, help="repeatable")
    p.add_argument("--duration", type=int, help="target length of the finished video, in seconds")
    p.add_argument("--score", type=int, choices=range(1, 11), metavar="1-10", help="how strong the idea is")
    p.add_argument("--person", action="append", default=[], help="who appears, as named in the knowledge base (repeatable)")
    add("check", cmd_check)
    p = add("set", cmd_set)
    p.add_argument("ids", nargs="+", metavar="ID")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--first", action="store_true", help="put these videos at the front of the production order")
    p.add_argument("--workdir", help="production folder of this video, relative to the project (edit/<type>-<slug>)")
    p.add_argument("--final", help="delivered file, relative to the project (final/<video folder>/<file>)")
    p.add_argument("--note", help="one line for the video's log (what the user said, what happened)")
    p = add("reset", cmd_reset)
    p.add_argument("--all", action="store_true", help="also the answers to the opening questions and every video plan")
    p.add_argument("--yes", action="store_true", help="the user confirmed; without it nothing is removed")
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
