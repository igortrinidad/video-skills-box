---
name: knowledge-base
description: Shared memory of the people, companies, products, events and content profiles behind the user's videos - one small markdown file per entry, in a "Base de conhecimento" folder next to the video projects, editable by hand. Use it whenever a name has to be spelled, identified or looked up (who is this person, what is this company, how is it written), when the user tells a fact about someone or something that appears in the videos ("the João is my partner", "it is spelled CreathorIA"), when a named person or company has to be researched on the web and remembered, when the user wants to see, fix or fill the knowledge base, and when a skill needs the content direction of a profile (audience, tone, themes, calls to action). The other video skills (context-extractor, content-explorer, produzir-video) read it before writing names or planning content.
---

# Knowledge base

Speech recognition writes "Criatoria" for CreathorIA and "Helder" for Elder, and footage never says who the man in the beige t-shirt is. One wrong name in a catalog ends up in subtitles, titles and captions. The knowledge base is where the right answer is written once and reused by every project: who people are, what companies are, how each name is spelled, and what kind of content each profile publishes.

The user edits these files by hand, so treat them as the user's document: add and correct, never rewrite a file wholesale, and never delete an entry without being asked.

**Windows:** `PYTHONUTF8=1` (PowerShell: `$env:PYTHONUTF8="1"`). Script: `python ~/.claude/skills/knowledge-base/scripts/kb.py <command>`. Every command prints JSON, except `digest`, which prints markdown.

## Where it lives

A folder whose name contains "conhecimento" or "knowledge", normally in the projects root, beside the projects:

```
<projects root>/
├── Base de conhecimento/
│   ├── LEIA-ME.md            instructions for the user (Portuguese)
│   ├── pessoas/<slug>.md     one file per person
│   ├── empresas/<slug>.md    one file per company, product, event, program or institution
│   ├── perfis/<slug>.md      content direction of each profile the videos are published on
│   └── termos.md             other words the transcription gets wrong ("Cláudio" for Claude)
├── Referencias gerais/
└── <Project>/
```

Files whose name starts with `_` are templates and are ignored. File names are lowercase, without accents, with hyphens: `joao-torrezani.md`.

The scripts look for it in this order: the folder given with `--from` and the two folders above it, then the projects root saved by `produzir-video`, then the folder saved with `kb.py where --set <folder>`. Pass `--from <project folder>` whenever you are working on a project.

## Commands

| Command | What it does |
|---|---|
| `kb.py where [--from <folder>]` | Which knowledge base applies, how many entries, which profiles. `knowledge_base: null` means there is none. |
| `kb.py init <projects root>` | Creates the folder, the templates, `LEIA-ME.md` and `termos.md`. Never overwrites. |
| `kb.py find "<name>" ["<name>" ...] [--from <folder>]` | For each name: the entry it matches (`match` is `name`, `alias`, `ambiguous` or `null`), its `status` and its file. Matches aliases and known misspellings, ignoring case and accents. |
| `kb.py add person\|organization "<Name>" --summary "..." [flags]` | Creates an entry. Refuses when the name already matches an entry and prints the file to edit instead. |
| `kb.py check [--from <folder>]` | Every entry with its status, `awaiting_confirmation` (not yet confirmed by the user), `draft_profiles`, and `problems` (invalid files). |
| `kb.py digest [--from <folder>] [--profile <name> \| --no-profile] [--out <file>]` | The whole base as one compact markdown text, for an agent that starts without context. |

If `where` finds no knowledge base, ask the user once whether to create it in the projects root, then run `init`.

## Entries

```markdown
---
name: Elder Freitas
aliases: [Elder]
heard_as: [Helder, Hélder]
relation: partner
organizations: [Clube das Startups]
summary: Um dos criadores do Clube das Startups; foi quem puxou a Ola SecretarIA para o ecossistema de inovação de Divinópolis.
appearance: óculos
status: confirmed
publish: ok
links: [https://www.instagram.com/elderfreitas]
updated: 2026-11-15
---

Confirmado por você: nome e Clube das Startups.

Achado na internet (conferir): advogado de startups em Divinópolis, consultor e professor.

No material: conta a história do ecossistema de inovação de Divinópolis.
```

- **name**: the correct spelling, exactly as it should appear in subtitles and captions.
- **aliases**: how the person or company is called in speech (first name, nickname, short name). An alias shared by two entries matches neither (`find` answers `ambiguous`), so "João" alone cannot be an alias while there are two Joãos.
- **heard_as**: how the transcription misspells it. Add every wrong spelling you meet; this is what lets the scripts fix names automatically.
- **relation**: for people `team`, `partner`, `client`, `investor`, `speaker`, `organizer`, `public-figure` or `other`; for organizations `own`, `partner`, `client`, `competitor`, `investor`, `organizer` or `other`. `team` and `own` mark the user's own people and companies, which go first into the transcription prompt.
- **organizations** (people): names equal to the `name` of entries in `empresas/`.
- **kind** (organizations): `company`, `product`, `event`, `program` or `institution`.
- **summary**: one or two sentences on who or what it is and how it relates to the user. It is the only prose most readers of the digest will see.
- **appearance** (people): traits that do not change from day to day (beard, glasses, hair). Clothing belongs to a project, not here.
- **status**: where the information came from. See the next section.
- **publish**: `ok`, `ask` (ask the user before publishing content that features or names this entry) or `avoid` (do not use).
- **links**: sources and profiles (site, Instagram, LinkedIn).
- **updated**: the date of the last change, `YYYY-MM-DD`.

The body is free notes in the user's language. Keep three kinds of information apart, each under its own opening words: `Confirmado por você:` (what the user said), `Achado na internet (conferir):` (web findings), `No material:` (what the footage shows). A reader must be able to tell a fact from a guess.

Write the frontmatter as valid YAML: a value with a colon, a quote or a `#` goes inside quotes.

## Status: who said it

| Status | Meaning | Who may set it |
|---|---|---|
| `confirmed` | The user said it or approved it. | Only after the user's own words in the conversation. |
| `researched` | Found on the web, with the sources in `links`. | You, after a search. |
| `unverified` | A guess from the footage or from context. | You. |

Never write `confirmed` on your own, however solid the source looks. A homonym on LinkedIn is the classic mistake, and the user cannot review what is labelled as already reviewed. When the user confirms only part of an entry (the spelling, but not the job title), set `confirmed` and keep the rest in the body under `Achado na internet (conferir):`.

## When a name comes up

Do this for every person or company named in footage, in a transcript or by the user, before writing the name anywhere:

1. `kb.py find "<name as heard>" --from <project>`.
2. **Match**: use the entry's `name`, exactly. If the spelling you heard is new, add it to the entry's `heard_as`.
3. **`ambiguous`**: two entries share that alias. Decide from context (company, appearance, who they are with); if you cannot, describe the person and leave the doubt written down for the user.
4. **No match**: research it (next section) and add it, so the next clip, project and skill already know.

## Researching a name on the web

A name alone is rarely enough; search with the context that makes it unique.

1. Search with what the footage gives: `"<name>" <company or role> <city or event>`. For a speaker at an event, the event's site or Instagram usually lists the line-up with the right spelling, which also fixes names you only half heard.
2. Prefer primary sources: the official site, the person's own profile, the event page. Open the page; do not trust a search snippet for a spelling.
3. Accept a result only when at least two details match what the footage shows (same company, same city, same face or role). A common name with one matching detail is a homonym until proven otherwise.
4. Save it:
   ```
   kb.py add person "Thiago Vinhal" --from <project> --status researched --relation speaker \
     --summary "Triatleta; palestrante do Divinópolis Summit 2026." \
     --org "Divinópolis Summit" --heard-as "Tiago Vinhau" \
     --link https://... --note "Achado na internet (conferir): ..."
   ```
   Organizations take `--kind` instead of `--org` and `--appearance`. Write `--summary` and `--note` in the user's language. `--alias`, `--heard-as`, `--org` and `--link` can be repeated.
5. Nothing reliable found: still add it, with `--status unverified`, a summary of what the footage shows and no links. An entry that says "investidor que conversou com Igor no Summit, sobrenome desconhecido" is more useful than no entry, because it stops the next agent from searching again.
6. Keep it proportional: a few searches per name. People who only pass through the frame and are never named do not get an entry.
7. Private individuals (not public figures, not speakers, not companies): record only what they said about themselves on camera and what the user tells you. Do not collect personal details from the web about them.

At the end of the task, list for the user what was added as `researched` or `unverified` and what you could not find, so they can confirm in one go. `kb.py check` gives the list (`awaiting_confirmation`).

## When the user tells you something

"João is my partner", "it is CreathorIA, with th", "don't post anything with her": update the entry right away, in the same turn.

- Entry exists: edit its file. Change only the fields involved, set `status: confirmed` if the user confirmed the identity, set `updated` to today, and add the fact to the body under `Confirmado por você:`.
- Entry missing: `kb.py add ... --status confirmed`.
- A word that is not a person or a company (a tool, a technical term, a slang word): add a line to `termos.md` as `- **Right spelling**: what it is. A transcrição escreve "wrong", "wrong".` The word in bold is what the scripts read.
- Then run `kb.py check` and fix anything under `problems`.

## Profiles: who the content is for

`perfis/<slug>.md` holds the content direction of one publishing profile: who speaks, audience, goals, tone, themes, formats, what to do and avoid, calls to action, visual identity. Frontmatter: `name`, `default` (`true` on the profile used when nobody says which), `status` (`confirmed` or `draft`), `handles` (`{instagram: "@...", youtube: "@..."}`), `language`.

- A skill that plans or writes content reads the profile first: `kb.py digest --from <project>` ends with the default profile; `--profile <name>` picks another.
- **`draft`** means the agent wrote it from what it observed and the user has not reviewed it. Use it as a hypothesis: say so to the user and confirm the direction before planning or producing from it. Only the user's review turns it into `confirmed`.
- When the base has several profiles and none is the default, the digest says so: ask the user which profile the content is for.
- When the user describes their audience, tone, limits or calls to action, write it into the profile in their words, replacing the matching "A decidir" lines.
- Never invent handles, links or numbers for a profile; leave them empty and ask.

## How the other skills use it

- **context-extractor**: `context.py prepare` writes the digest (without the profile) to `<project>/edit/context/knowledge.md` and adds the names to the transcription prompt; `context.py labels` rewrites the people named in the insight files with the entry names.
- **content-explorer** and **produzir-video**: read `kb.py digest --from <project>` for names, spellings, `publish` restrictions and the content direction before proposing or writing titles, captions and on-screen text.
- From Python: `from videokit import knowledge` (`find_kb`, `load_entries`, `resolve`, `canonical`, `digest`), documented in the `video-toolkit` skill.

A digest is a snapshot. After changing the knowledge base, regenerate any digest a later step will read.
