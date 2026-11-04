"""Folder conventions for the video projects root.

    raiz/
    ├── Referencias gerais/        any name containing "referenc"
    │   ├── Elementos graficos gerais/
    │   ├── Videos de referencia/<tipo>/<nome>/
    │   ├── Assets/                logos, images, prints shared by every project
    │   ├── Sons/
    │   └── Motions/
    └── <Projeto>/
        ├── raw/      footage (aliases: material_bruto, brutos, bruto)
        ├── assets/   project-only images, prints, logos (aliases: imagens, arquivos)
        ├── refs/     project-only references (aliases: referencia, referencias)
        ├── edit/     everything the skills generate
        └── final/    deliverables: "YYYY-MM-DD_HHMM - Titulo.ext"

Usage:
    python projeto.py raiz                       # last root used (JSON)
    python projeto.py raiz --set <pasta>
    python projeto.py scan <raiz>                # references + projects (JSON)
    python projeto.py init <pasta_projeto>       # resolve/create raw, assets, refs, edit, final (JSON)
    python projeto.py entregar <arquivo> --projeto <pasta> --titulo "Titulo" [--copiar] [--quando ISO]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))
from videokit.media import MEDIA_EXTS  # noqa: E402

CONFIG = Path.home() / ".config" / "video-skills" / "config.json"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".psd"}
MOTION_EXTS = {".mov", ".webm", ".mp4", ".json", ".lottie", ".gif", ".html", ".mogrt", ".aep"}

RAW_ALIASES = ["raw", "material_bruto", "material bruto", "brutos", "bruto"]
REFS_ALIASES = ["refs", "referencia", "referencias"]
ASSETS_ALIASES = ["assets", "asset", "imagens", "arquivos"]
# category -> keywords matched against the normalized folder name (first match wins)
REF_CATEGORIES = {
    "assets": ["asset", "imagen", "logo", "print", "foto", "arquivo"],
    "videos": ["video"],
    "elementos": ["element", "grafic", "legenda", "placa", "overlay"],
    "sons": ["som", "sons", "audio", "musica", "trilha", "sfx"],
    "motions": ["motion", "animac", "transic"],
}
SKIP_DIRS = {"_analise", "__pycache__", ".git"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def dump(obj) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def find_alias(folder: Path, aliases: list[str]) -> Path | None:
    by_name = {norm(p.name): p for p in folder.iterdir() if p.is_dir()}
    for a in aliases:
        if a in by_name:
            return by_name[a]
    return None


def is_project(folder: Path) -> bool:
    return find_alias(folder, RAW_ALIASES) is not None or any(
        p.suffix.lower() in MEDIA_EXTS for p in folder.iterdir() if p.is_file())


def files_in(folder: Path, root: Path) -> list[dict]:
    out = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        if p.name in {"estilo.md", "analise_log.txt"} or p.name.startswith("."):
            continue
        out.append({"arquivo": str(p.relative_to(root)), "nome": p.stem,
                    "tipo": p.suffix.lower().lstrip("."), "mb": round(p.stat().st_size / 1e6, 1)})
    return out


def scan_references(ref_root: Path) -> dict:
    cats: dict = {k: [] for k in REF_CATEGORIES}
    cats["outros"] = []
    for sub in sorted(p for p in ref_root.iterdir() if p.is_dir()):
        n = norm(sub.name)
        cat = next((c for c, kws in REF_CATEGORIES.items() if any(k in n for k in kws)), "outros")
        entry = {"pasta": sub.name, "arquivos": files_in(sub, ref_root)}
        if cat == "videos":
            # Videos de referencia/<tipo>/<nome>/ : expose each reference with its estilo.md, if any
            refs = []
            for tipo in sorted(p for p in sub.iterdir() if p.is_dir()):
                for ref in sorted([tipo, *[p for p in tipo.iterdir() if p.is_dir() and p.name not in SKIP_DIRS]]):
                    vids = [p for p in ref.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTS]
                    if vids:
                        estilo = ref / "estilo.md"
                        refs.append({"tipo": tipo.name, "nome": ref.name, "pasta": str(ref),
                                     "videos": [v.name for v in vids],
                                     "estilo": str(estilo) if estilo.exists() else None})
            entry["referencias"] = refs
            del entry["arquivos"]
        cats[cat].append(entry)
    return {"pasta": str(ref_root), **cats}


def cmd_raiz(args) -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    if args.set:
        root = Path(args.set).expanduser().resolve()
        if not root.is_dir():
            sys.exit(f"pasta não encontrada: {root}")
        cfg["raiz"] = str(root)
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    raiz = cfg.get("raiz")
    dump({"raiz": raiz, "existe": bool(raiz and Path(raiz).is_dir())})


def cmd_scan(args) -> None:
    root = Path(args.raiz).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"pasta não encontrada: {root}")
    refs, projects = [], []
    for sub in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if "referenc" in norm(sub.name) and not is_project(sub):
            refs.append(scan_references(sub))
        else:
            raw = find_alias(sub, RAW_ALIASES)
            final = sub / "final"
            assets = find_alias(sub, ASSETS_ALIASES)
            projects.append({
                "nome": sub.name, "pasta": str(sub),
                "raw": str(raw) if raw else None,
                "assets": files_in(assets, sub) if assets else [],
                "refs": str(r) if (r := find_alias(sub, REFS_ALIASES)) else None,
                "tem_edit": (sub / "edit").is_dir(),
                "finais": sorted(p.name for p in final.iterdir()) if final.is_dir() else [],
                "fora_do_padrao": raw is None or norm(raw.name) != "raw",
            })
    dump({"raiz": str(root), "referencias_gerais": refs, "projetos": projects})


def cmd_init(args) -> None:
    proj = Path(args.projeto).expanduser().resolve()
    if not proj.is_dir():
        sys.exit(f"pasta não encontrada: {proj}")
    raw = find_alias(proj, RAW_ALIASES)
    loose = sorted(p.name for p in proj.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTS)
    assets = find_alias(proj, ASSETS_ALIASES) or proj / "assets"
    assets.mkdir(exist_ok=True)
    (proj / "edit").mkdir(exist_ok=True)
    (proj / "final").mkdir(exist_ok=True)
    refs = find_alias(proj, REFS_ALIASES)
    raw_files = sorted(p.name for p in raw.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTS) if raw else []
    dump({
        "projeto": str(proj), "raw": str(raw) if raw else None, "raw_arquivos": raw_files,
        "midia_solta_na_raiz_do_projeto": loose,
        "assets": str(assets), "assets_arquivos": files_in(assets, proj),
        "refs": str(refs) if refs else None, "refs_estilo": str(refs / "estilo.md") if refs and (refs / "estilo.md").exists() else None,
        "edit": str(proj / "edit"), "final": str(proj / "final"),
        "project_md": str(proj / "edit" / "project.md") if (proj / "edit" / "project.md").exists() else None,
    })


def safe_title(title: str) -> str:
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip().rstrip(". ")
    return re.sub(r"\s+", " ", t)[:120] or "video"


def cmd_entregar(args) -> None:
    src = Path(args.arquivo).expanduser().resolve()
    if not src.is_file():
        sys.exit(f"arquivo não encontrado: {src}")
    final = Path(args.projeto).expanduser().resolve() / "final"
    final.mkdir(parents=True, exist_ok=True)
    when = datetime.fromisoformat(args.quando) if args.quando else datetime.now()
    dest = final / f"{when:%Y-%m-%d_%H%M} - {safe_title(args.titulo)}{src.suffix.lower()}"
    n = 2
    while dest.exists():
        dest = final / f"{when:%Y-%m-%d_%H%M} - {safe_title(args.titulo)} ({n}){src.suffix.lower()}"
        n += 1
    (shutil.copy2 if args.copiar else shutil.move)(str(src), str(dest))
    dump({"entregue": str(dest)})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("raiz"); p.add_argument("--set"); p.set_defaults(fn=cmd_raiz)
    p = sub.add_parser("scan"); p.add_argument("raiz"); p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("init"); p.add_argument("projeto"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("entregar")
    p.add_argument("arquivo"); p.add_argument("--projeto", required=True); p.add_argument("--titulo", required=True)
    p.add_argument("--copiar", action="store_true", help="copia em vez de mover")
    p.add_argument("--quando", help="data/hora ISO (padrão: agora)")
    p.set_defaults(fn=cmd_entregar)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
