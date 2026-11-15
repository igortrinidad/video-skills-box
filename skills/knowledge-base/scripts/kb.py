"""Knowledge base of people, companies and content profiles, shared by every video project.

Usage:
    python kb.py where [--from <folder>] [--set <kb folder>]   # which knowledge base applies (JSON)
    python kb.py init <projects root>                          # create "Base de conhecimento" with templates
    python kb.py check [--from <folder>]                       # entries, what awaits confirmation, problems (JSON)
    python kb.py find <name> [<name> ...] [--from <folder>]    # is this name known? (JSON)
    python kb.py add person|organization <name> --summary "..." [--status researched] [--link <url>] ...
    python kb.py digest [--from <folder>] [--profile <name> | --no-profile] [--out <file>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))
from videokit import knowledge  # noqa: E402
from videokit.project import find_alias, load_config, norm, save_config  # noqa: E402

KB_NAME = "Base de conhecimento"

README = """# Base de conhecimento

Tudo o que as skills de vídeo precisam saber sobre quem aparece nos vídeos e para quem o conteúdo é feito.
Vale para todos os projetos desta pasta. Pode editar à mão: cada arquivo `.md` é uma ficha.

- `pessoas/`: uma ficha por pessoa (sócios, equipe, clientes, palestrantes, investidores).
- `empresas/`: uma ficha por empresa, produto, evento, programa ou instituição.
- `perfis/`: a direção de conteúdo de cada perfil onde os vídeos são publicados.
- `termos.md`: outras palavras que a transcrição costuma errar.

Para criar uma ficha, copie o `_modelo.md` da pasta, renomeie (minúsculas, sem acento, com hífen:
`joao-torrezani.md`) e preencha. Arquivos que começam com `_` são ignorados.

`status` diz de onde veio a informação: `confirmed` (você confirmou), `researched` (achado na internet,
com os links em `links`) ou `unverified` (palpite). Troque para `confirmed` quando conferir.
"""

PERSON = """---
name: Nome Completo
aliases: []            # como a pessoa é chamada: [João, Jô]
heard_as: []           # como a transcrição escreve errado: [Torresani]
relation: other        # team | partner | client | investor | speaker | organizer | public-figure | other
organizations: []      # nomes iguais aos das fichas em empresas/
summary: Uma ou duas frases sobre quem é e qual a relação com vocês.
appearance:            # traços que não mudam de um dia para o outro (barba, óculos, cabelo)
status: unverified     # confirmed | researched | unverified
publish: ok            # ok | ask (perguntar antes de publicar) | avoid (não usar)
links: []
updated: 2026-01-01
---

Notas livres: histórico, assuntos em que é referência, cuidados ao citar.
"""

ORGANIZATION = """---
name: Nome Oficial
kind: company          # company | product | event | program | institution
aliases: []
heard_as: []           # como a transcrição escreve errado
relation: other        # own | partner | client | competitor | investor | organizer | other
summary: O que é, em uma ou duas frases.
status: unverified     # confirmed | researched | unverified
publish: ok            # ok | ask | avoid
links: []              # site, Instagram
updated: 2026-01-01
---

Notas livres: como apresentar, números que podem ser ditos, o que não divulgar.
"""

PROFILE = """---
name: Nome do perfil
default: false         # true no perfil usado quando ninguém diz qual é
status: confirmed      # draft = rascunho que você ainda não revisou
handles: {}            # {instagram: "@perfil", youtube: "@canal", tiktok: "@perfil"}
language: pt-BR
---

## Quem fala
Quem é a pessoa ou marca, de onde fala e por que alguém deveria ouvir.

## Público
Para quem é o conteúdo e o que essa pessoa quer resolver.

## Objetivos
O que o conteúdo precisa gerar (autoridade, clientes, comunidade, bastidores).

## Tom
Como soa. Humor, palavrão, gíria: o que pode e até onde.

## Temas
Os assuntos de que o perfil trata, em ordem de importância.

## Formatos que funcionam
O que já deu certo e o que o perfil quer testar.

## Fazer
- 

## Evitar
- 

## Chamadas para ação
O que pedir no fim de um vídeo, com os links.

## Identidade visual
Cores, fontes, logo e onde estão os arquivos (por exemplo em `Referencias gerais/`).
"""

TERMS = """# Termos

Palavras que a transcrição costuma errar e que não são pessoa nem empresa. Uma por linha:

- **Claude**: assistente de IA da Anthropic. A transcrição escreve "Cláudio", "Clod".
"""


def dump(obj) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def locate(args) -> Path:
    start = Path(args.from_).expanduser() if args.from_ else None
    kb = knowledge.find_kb(start)
    if not kb:
        sys.exit("no knowledge base found: create one with `kb.py init <projects root>`")
    return kb


def cmd_where(args) -> None:
    if args.set:
        folder = Path(args.set).expanduser().resolve()
        if not knowledge.is_kb(folder):
            sys.exit(f"not a knowledge base (name must contain 'conhecimento' or 'knowledge' and it needs "
                     f"a pessoas/, empresas/ or perfis/ folder): {folder}")
        save_config({**load_config(), "base_conhecimento": str(folder)})
    start = Path(args.from_).expanduser() if args.from_ else None
    kb = knowledge.find_kb(start)
    entries = knowledge.load_entries(kb)[0] if kb else []
    dump({"knowledge_base": str(kb) if kb else None,
          "entries": {k: sum(e["kind"] == k for e in entries) for k in knowledge.FOLDERS},
          "profiles": knowledge.pick_profile(entries)[1],
          "projects_root": load_config().get("raiz")})


def cmd_init(args) -> None:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"folder not found: {root}")
    existing = [p for p in [root, *root.iterdir()] if p.is_dir() and any(w in norm(p.name) for w in knowledge.KB_WORDS)]
    kb = existing[0] if existing else root / KB_NAME
    created = []
    for kind, template in (("person", PERSON), ("organization", ORGANIZATION), ("profile", PROFILE)):
        folder = find_alias(kb, knowledge.FOLDERS[kind]) if kb.is_dir() else None
        folder = folder or kb / knowledge.FOLDERS[kind][0]
        folder.mkdir(parents=True, exist_ok=True)
        for path, text in ((folder / "_modelo.md", template),):
            if not path.exists():
                path.write_text(text, encoding="utf-8", newline="\n")
                created.append(str(path))
    for name, text in (("LEIA-ME.md", README), (knowledge.TERMS_FILES[0], TERMS)):
        if name == knowledge.TERMS_FILES[0] and any((kb / n).exists() for n in knowledge.TERMS_FILES):
            continue
        if not (kb / name).exists():
            (kb / name).write_text(text, encoding="utf-8", newline="\n")
            created.append(str(kb / name))
    dump({"knowledge_base": str(kb), "created": created})


def cmd_check(args) -> None:
    kb = locate(args)
    entries, problems = knowledge.load_entries(kb)
    seen: dict[str, str] = {}
    for e in entries:
        if e["kind"] == "profile":
            continue
        key = norm(e["meta"]["name"])
        if key in seen:
            problems.append({"file": e["file"], "problems": [f"same name as {seen[key]}"]})
        seen[key] = e["file"]
    rows = [{"kind": e["kind"], "name": e["meta"]["name"], "status": e["meta"].get("status"),
             "file": Path(e["file"]).relative_to(kb).as_posix()} for e in entries]
    dump({"knowledge_base": str(kb), "entries": rows,
          "awaiting_confirmation": [r["name"] for r in rows if r["kind"] != "profile" and r["status"] != "confirmed"],
          "draft_profiles": [r["name"] for r in rows if r["kind"] == "profile" and r["status"] == "draft"],
          "problems": problems})


def cmd_add(args) -> None:
    kb = locate(args)
    entries, _ = knowledge.load_entries(kb)
    hit, _ = knowledge.resolve(entries, args.name)
    if hit:
        sys.exit(f"already in the knowledge base as \"{hit['meta']['name']}\": edit {hit['file']}")
    person = args.type == "person"
    meta: dict = {"name": args.name.strip()}
    if not person:
        meta["kind"] = args.kind
    meta |= {"aliases": args.alias, "heard_as": args.heard_as, "relation": args.relation}
    if person:
        meta["organizations"] = args.org
    meta["summary"] = args.summary.strip()
    if person:
        meta["appearance"] = args.appearance
    meta |= {"status": args.status, "publish": args.publish, "links": args.link, "updated": date.today()}
    folder = find_alias(kb, knowledge.FOLDERS[args.type]) or kb / knowledge.FOLDERS[args.type][0]
    path = folder / (re.sub(r"[^a-z0-9]+", "-", norm(args.name)).strip("-") + ".md")
    if path.exists():
        sys.exit(f"file already exists: {path}")
    folder.mkdir(parents=True, exist_ok=True)
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=10 ** 9)
    path.write_text(f"---\n{front}---\n\n{(args.note or '').strip()}\n", encoding="utf-8", newline="\n")
    dump({"created": str(path), "name": meta["name"], "status": args.status})


def cmd_find(args) -> None:
    kb = locate(args)
    entries, _ = knowledge.load_entries(kb)
    out = []
    for name in args.names:
        e, how = knowledge.resolve(entries, name)
        out.append({"query": name, "match": how, "name": e["meta"]["name"] if e else None,
                    "status": e["meta"].get("status") if e else None, "file": e["file"] if e else None})
    dump(out)


def cmd_digest(args) -> None:
    kb = locate(args)
    text = knowledge.digest(kb, args.profile, with_profile=not args.no_profile)
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        dump({"digest": str(out), "knowledge_base": str(kb)})
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name: str, fn):
        p = sub.add_parser(name)
        p.add_argument("--from", dest="from_", help="project or folder to start looking from")
        p.set_defaults(fn=fn)
        return p

    add("where", cmd_where).add_argument("--set", help="knowledge base to use when none is found near the project")
    p = sub.add_parser("init"); p.add_argument("root"); p.set_defaults(fn=cmd_init)
    add("check", cmd_check)
    add("find", cmd_find).add_argument("names", nargs="+")
    p = add("add", cmd_add)
    p.add_argument("type", choices=["person", "organization"])
    p.add_argument("name", help="correct spelling, as it should appear in subtitles")
    p.add_argument("--summary", required=True, help="one or two sentences: who or what it is")
    p.add_argument("--status", choices=knowledge.STATUSES, default="unverified")
    p.add_argument("--relation", default="other",
                   help="person: team|partner|client|investor|speaker|organizer|public-figure|other; "
                        "organization: own|partner|client|competitor|investor|organizer|other")
    p.add_argument("--kind", default="company", help="organization only: company|product|event|program|institution")
    p.add_argument("--alias", action="append", default=[], help="how it is called (repeatable)")
    p.add_argument("--heard-as", action="append", default=[], help="how the transcription misspells it (repeatable)")
    p.add_argument("--org", action="append", default=[], help="person only: organization entry name (repeatable)")
    p.add_argument("--appearance", help="person only: traits that do not change from day to day")
    p.add_argument("--publish", choices=knowledge.PUBLISH, default="ok")
    p.add_argument("--link", action="append", default=[], help="source or profile URL (repeatable)")
    p.add_argument("--note", help="free notes for the body of the file")
    p = add("digest", cmd_digest)
    p.add_argument("--profile", help="profile name or file name (default: the one marked `default: true`)")
    p.add_argument("--no-profile", action="store_true", help="people, companies and terms only")
    p.add_argument("--out")
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
