"""Knowledge base shared by the skills (format documented in the knowledge-base skill).

    <projects root>/Base de conhecimento/   a folder whose name contains "conhecimento" or "knowledge"
    ├── pessoas/<slug>.md    people                                         (alias: people)
    ├── empresas/<slug>.md   companies, products, events, institutions      (alias: organizations)
    ├── perfis/<slug>.md     content direction of each publishing profile   (alias: profiles)
    └── termos.md            other words the transcription gets wrong       (alias: terms.md)
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import yaml

from .project import find_alias, load_config, norm

KB_WORDS = ("conhecimento", "knowledge")
FOLDERS = {
    "person": ["pessoas", "people"],
    "organization": ["empresas", "organizacoes", "organizations"],
    "profile": ["perfis", "profiles"],
}
TERMS_FILES = ["termos.md", "terms.md"]
STATUSES = ["confirmed", "researched", "unverified"]
PUBLISH = ["ok", "ask", "avoid"]
LIST_KEYS = ("aliases", "heard_as", "organizations", "links")
OWN_RELATIONS = ("team", "own")


def split_frontmatter(text: str) -> tuple[dict | None, str, str | None]:
    """(frontmatter, body, error). The frontmatter is None when it is missing or invalid."""
    m = re.match(r"---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    if not m:
        return None, text, "no YAML frontmatter"
    try:
        fm = yaml.safe_load(m[1])
    except yaml.YAMLError as e:
        return None, text[m.end():], f"frontmatter is not valid YAML: {str(e).splitlines()[0]}"
    if not isinstance(fm, dict):
        return None, text[m.end():], "frontmatter is not a mapping"
    return fm, text[m.end():], None


def is_kb(folder: Path) -> bool:
    """The entry folders are required too, so a project that is merely about knowledge is not taken for one."""
    return (folder.is_dir() and any(w in norm(folder.name) for w in KB_WORDS)
            and any(find_alias(folder, a) for a in FOLDERS.values()))


def find_kb(start: Path | None = None) -> Path | None:
    """Nearest knowledge base: in `start` or up to two folders above it, then in the configured
    projects root, then the one saved with `kb.py where --set`."""
    cfg = load_config()
    places: list[Path] = []
    if start:
        start = start.resolve()
        places += [start, *list(start.parents)[:2]]
    if cfg.get("raiz"):
        places.append(Path(cfg["raiz"]))
    for folder in places:
        if not folder.is_dir():
            continue
        for p in [folder, *sorted(folder.iterdir())]:
            if is_kb(p):
                return p
    saved = cfg.get("base_conhecimento")
    return Path(saved) if saved and Path(saved).is_dir() else None


def load_entries(kb: Path) -> tuple[list[dict], list[dict]]:
    """(entries, problems). An entry is {kind, file, meta, body}; files starting with "_" are templates."""
    entries, problems = [], []
    for kind, aliases in FOLDERS.items():
        folder = find_alias(kb, aliases)
        for f in sorted(folder.glob("*.md")) if folder else []:
            if f.name.startswith("_"):
                continue
            fm, body, err = split_frontmatter(f.read_text(encoding="utf-8-sig"))
            issues = [err] if err else []
            if fm is not None:
                if not isinstance(fm.get("name"), str) or not fm["name"].strip():
                    issues.append("`name` is missing")
                issues += [f"`{k}` must be a list" for k in LIST_KEYS if not isinstance(fm.get(k) or [], list)]
                if kind != "profile":
                    if not isinstance(fm.get("summary"), str) or not fm["summary"].strip():
                        issues.append("`summary` is missing")
                    if fm.get("status") not in STATUSES:
                        issues.append(f"`status` must be one of {STATUSES}")
                    if fm.get("publish", "ok") not in PUBLISH:
                        issues.append(f"`publish` must be one of {PUBLISH}")
            if issues:
                problems.append({"file": str(f), "problems": issues})
            if fm is not None and isinstance(fm.get("name"), str) and fm["name"].strip():
                entries.append({"kind": kind, "file": str(f), "meta": fm, "body": body.strip()})
    return entries, problems


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", norm(s))


def _strings(v) -> list[str]:
    return [str(x) for x in v] if isinstance(v, list) else []


def resolve(entries: list[dict], label: str) -> tuple[dict | None, str | None]:
    """Match a label to a person or organization: (entry, "name" | "alias") or (None, "ambiguous" | None).
    A trailing note in parentheses is ignored, and an alias only counts when a single entry has it."""
    pool = [e for e in entries if e["kind"] != "profile"]
    keys = list(dict.fromkeys([_key(label), _key(re.sub(r"\(.*?\)", " ", label))]))
    for k in keys:
        for e in pool:
            if _key(e["meta"]["name"]) == k:
                return e, "name"
    for k in keys:
        hits = [e for e in pool
                if k in {_key(a) for a in _strings(e["meta"].get("aliases")) + _strings(e["meta"].get("heard_as"))}]
        if len(hits) == 1:
            return hits[0], "alias"
        if hits:
            return None, "ambiguous"
    return None, None


def canonical(entries: list[dict], label: str) -> str | None:
    """The label written with the entry's name, keeping a note in parentheses; None when no entry matches."""
    e, _ = resolve(entries, label)
    if not e:
        return None
    m = e["meta"]
    name = m["name"].strip()
    if _key(label) in {_key(x) for x in [name, *_strings(m.get("aliases")), *_strings(m.get("heard_as"))]}:
        return name
    return " ".join([name, *re.findall(r"\(.*?\)", label)])


def label_status(entries: list[dict], label: str) -> tuple[str, str | None]:
    """How a `people` label of an insight file relates to the knowledge base: (state, label to use).

    known      names an entry; the label to use differs when it was written with an alias or a misspelling
    inferred   names an entry, with a note in parentheses saying the identification is inferred or presumed
    unknown    a name (starts with a capital letter) that no entry has
    described  a description of someone nobody named ("man in navy event shirt")
    """
    new = canonical(entries, label)
    if new is None:
        return ("unknown" if re.match(r"[A-ZÀ-Ý][a-zà-ÿ]", label.strip()) else "described"), None
    note = " ".join(re.findall(r"\((.*?)\)", label)).lower()
    return ("inferred" if re.search(r"inferred|presumed|inferid|presumid", note) else "known"), new


def spot(entries: list[dict], text: str) -> list[tuple[str, list[str]]]:
    """Names, aliases and known misspellings found in `text`: [(as written, entry names it may refer to)].
    Several names mean the spelling is shared and the context has to decide."""
    written: dict[str, str] = {}
    names: dict[str, list[str]] = {}
    for e in entries:
        if e["kind"] == "profile":
            continue
        m = e["meta"]
        for s in dict.fromkeys([m["name"], *_strings(m.get("aliases")), *_strings(m.get("heard_as"))]):
            s = s.strip()
            if s and re.search(rf"(?<!\w){re.escape(s)}(?!\w)", text, re.I):
                written.setdefault(_key(s), s)
                names.setdefault(_key(s), [])
                if m["name"].strip() not in names[_key(s)]:
                    names[_key(s)].append(m["name"].strip())
    # A short form inside a longer match of the same entry ("Elder" in "Elder Freitas") adds nothing
    keep = [k for k in names
            if not any(k != o and k in o and names[k] == names[o] for o in names)]
    return [(written[k], names[k]) for k in sorted(keep)]


def terms(kb: Path) -> list[str]:
    """The words in bold in termos.md: the correct spelling of terms that are not a person or a company."""
    path = next((kb / n for n in TERMS_FILES if (kb / n).exists()), None)
    return re.findall(r"^\s*[-*]\s*\*\*(.+?)\*\*", path.read_text(encoding="utf-8-sig"), re.M) if path else []


def prompt_terms(entries: list[dict], extra: list[str] | None = None, limit: int = 350) -> str:
    """Names for the transcription prompt (it biases spelling): own team and companies, then `extra`,
    then what the user confirmed, then the rest. Cut at `limit` because the prompt is short."""
    pool = sorted((e for e in entries if e["kind"] != "profile"),
                  key=lambda e: (STATUSES.index(e["meta"]["status"]) if e["meta"].get("status") in STATUSES else 9,
                                 _key(e["meta"]["name"])))
    own = [e["meta"]["name"].strip() for e in pool if str(e["meta"].get("relation")) in OWN_RELATIONS]
    rest = [e["meta"]["name"].strip() for e in pool if str(e["meta"].get("relation")) not in OWN_RELATIONS]
    out = ""
    for name in dict.fromkeys([*own, *(extra or []), *rest]):
        if len(out) + len(name) + 2 > limit:
            break
        out += (", " if out else "") + name
    return out


def pick_profile(entries: list[dict], name: str | None = None) -> tuple[dict | None, list[str]]:
    """(profile, all profile names). Without a name: the one marked `default: true`, or the only one."""
    profiles = [e for e in entries if e["kind"] == "profile"]
    names = [e["meta"]["name"] for e in profiles]
    if name:
        wanted = _key(name)
        hit = [e for e in profiles if wanted in {_key(e["meta"]["name"]), _key(Path(e["file"]).stem)}]
        return (hit[0] if hit else None), names
    default = [e for e in profiles if e["meta"].get("default") is True]
    if len(default) == 1:
        return default[0], names
    return (profiles[0] if len(profiles) == 1 else None), names


def _line(e: dict) -> str:
    m = e["meta"]
    notes = []
    if m.get("kind"):
        notes.append(str(m["kind"]))
    if _strings(m.get("aliases")):
        notes.append("also: " + ", ".join(_strings(m["aliases"])))
    if _strings(m.get("heard_as")):
        notes.append("transcribed as: " + ", ".join(f'"{h}"' for h in _strings(m["heard_as"])))
    out = f"- **{m['name']}**" + (f" ({'; '.join(notes)})" if notes else "") + f": {str(m.get('summary') or '').strip()}"
    if _strings(m.get("organizations")):
        out += f" Organizations: {', '.join(_strings(m['organizations']))}."
    if m.get("appearance"):
        out += f" Appearance: {m['appearance']}."
    if m.get("status") != "confirmed":
        out += f" [{m.get('status')}]"
    if m.get("publish", "ok") != "ok":
        out += f" [publish: {m['publish']}]"
    return out


def digest(kb: Path, profile: str | None = None, with_profile: bool = True) -> str:
    """Compact view of the whole knowledge base for an agent that starts without context."""
    entries, _ = load_entries(kb)
    out = ["# Knowledge digest", "",
           f"Generated on {date.today().isoformat()} from `{kb}`. Edit the knowledge base, not this file.", "",
           "Names in bold are the correct spelling: use them exactly. `[researched]` came from the web and "
           "`[unverified]` is a guess; entries without a mark were confirmed by the user.", ""]
    for kind, title in (("person", "People"), ("organization", "Companies, products, events and institutions")):
        rows = [_line(e) for e in entries if e["kind"] == kind]
        if rows:
            out += [f"## {title}", "", *rows, ""]
    terms = next((kb / n for n in TERMS_FILES if (kb / n).exists()), None)
    if terms:
        text = re.sub(r"^# .*\n", "", terms.read_text(encoding="utf-8-sig").strip()).strip()
        if text:
            out += ["## Other terms", "", text, ""]
    if not with_profile:
        return "\n".join(out)
    chosen, names = pick_profile(entries, profile)
    if chosen:
        out += [f"## Content direction: {chosen['meta']['name']}", ""]
        if chosen["meta"].get("status") == "draft":
            out += ["This profile is a draft the user has not reviewed: treat it as a hypothesis and confirm "
                    "the direction with the user before planning or producing content from it.", ""]
        out += [chosen["body"], ""]
        others = [n for n in names if n != chosen["meta"]["name"]]
        if others:
            out += [f"Other profiles in the knowledge base: {', '.join(others)}.", ""]
    elif names:
        out += ["## Content direction", "",
                f"Several profiles and none chosen: {', '.join(names)}. Ask the user which one this content is for.", ""]
    return "\n".join(out)
