"""Project folder conventions shared by the skills (layout documented in produzir-video)."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

CONFIG = Path.home() / ".config" / "video-skills" / "config.json"
RAW_ALIASES = ["raw", "material_bruto", "material bruto", "brutos", "bruto"]


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}


def save_config(cfg: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def find_alias(folder: Path, aliases: list[str]) -> Path | None:
    by_name = {norm(p.name): p for p in folder.iterdir() if p.is_dir()}
    for a in aliases:
        if a in by_name:
            return by_name[a]
    return None


def raw_dir(project: Path) -> Path | None:
    """The project's footage folder, or None when the media sits loose in the project folder."""
    return find_alias(project, RAW_ALIASES)


def reference_dirs(project: Path) -> list[Path]:
    """Shared production references ("Referencias gerais": graphics, sounds, reference videos) that apply
    to a project: folders with "referenc" in the name up to two levels above it or in the projects root."""
    places = list(project.resolve().parents)[:2]
    root = load_config().get("raiz")
    if root:
        places.append(Path(root))
    out: list[Path] = []
    for folder in places:
        if not folder.is_dir():
            continue
        for p in sorted(folder.iterdir()):
            if p.is_dir() and "referenc" in norm(p.name) and raw_dir(p) is None and p not in out:
                out.append(p)
    return out
