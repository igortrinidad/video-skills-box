---
name: content-explorer
description: Explores footage that was already catalogued by context-extractor and proposes the videos worth making from it - shorts (Reels, TikTok, YouTube Shorts) and long videos (YouTube vlogs and the like) in the styles the user picks (fun, technical, vlog, provocative, story...) - each as a plan with the exact clips and time ranges. It asks the styles, formats and quantity first, saves every step so the work can be resumed, waits for the user to approve which videos to produce and in which order, hands each approved video to produzir-video, and keeps a status file per video. Use it whenever the user asks what content, videos, shorts, reels, cuts or themes can come out of a shoot, event or project ("que vídeos dá para fazer com isso?", "explora o material", "sugere conteúdos", "quero shorts do evento"), wants to approve, reorder, continue or check the status of planned videos, or asks to restart the exploration.
---

# Content explorer

A shoot of two hundred clips holds maybe fifteen videos worth posting, and they are not where the files suggest: a punchline at minute three of a long conversation, a story that starts in one clip and pays off four hours later. This skill reads the catalogued footage, proposes those videos as concrete plans, and produces only what the user approves.

It plans and tracks. The footage context comes from `context-extractor`, names and the content direction from `knowledge-base`, and the editing is done by `produzir-video`.

**Windows:** `PYTHONUTF8=1` (PowerShell: `$env:PYTHONUTF8="1"`). Script: `python ~/.claude/skills/content-explorer/scripts/explore.py <command> <project>`. Every command prints JSON.

Talk to the user in their language. Write the plans in the language of the footage.

## Where things go

```
<project>/edit/explore/
├── session.json            the user's answers (styles, formats, quantity, profile, references) and the batches
├── knowledge.md            digest of the knowledge base with the content direction (generated)
├── material/<batch>.md     the insight files of one batch of clips, joined (generated)
├── notes/<batch>.md        what was found in that batch (you write this)
├── videos/<ID>-<slug>.md   one file per video: the plan, with the status in the frontmatter
└── overview.md             every video by status (generated; show this to the user)
```

One file per video and per batch is what lets several agents work at once without overwriting each other. Never edit `overview.md`, `material/` or `knowledge.md`: they are rebuilt from the other files.

## Always start with `status`

Run `explore.py status <project>` before anything else, every time. Its `next` field says which step the project is in, so work that was interrupted continues instead of starting again:

| `next` starts with | Do |
|---|---|
| `context:` | The footage is not catalogued. Run the `context-extractor` skill on the project, then come back. |
| `ask:` | Step 1. |
| `material:` | Run `explore.py material <project>`, then step 3 for the batches not `done`. |
| `scout:` | Step 3, only for the batches whose `notes` is `missing` or `stale`. |
| `plan:` | Step 4. |
| `fix:` | Run `check` and correct the files it lists. |
| `approve:` | Step 5. |
| `produce:` | Step 7. |
| `review:` | Step 8. |
| `done:` | Tell the user everything is delivered and ask whether to look for more ideas. |

When the session already exists, tell the user in one or two lines where things stand (what they asked for, how many videos in each status) before continuing. Do not ask the opening questions again.

**The user asks to restart** ("começa de novo", "refaz a exploração", "zera"): do not delete anything yet. Run `explore.py reset <project>` (add `--all` if they also want to change the styles and formats and drop every plan). Without `--yes` it only reports what would be removed and what is kept. Tell the user those numbers in plain words, including that approved and produced videos are kept unless they ask for everything, and run it again with `--yes` only after they confirm. What is removed is moved to `edit/explore-old/<date>/`, not erased. If they only want different styles or a different quantity, `start --update` changes the answers without losing anything.

## Flow

### 1. Ask before exploring

Ask everything in one go, with the question tool of your environment when there is one (multiple choice), otherwise in a single message. Skip what the user already said in the request.

1. **Styles** (several can be chosen): offer the catalogue below with the names in the user's language, with the ones that fit the profile's tone first. The user may name a style that is not in the list.
2. **Format** (several can be chosen): Shorts (Reels, TikTok, YouTube Shorts) and/or Long (YouTube and the like).
3. **Quantity** (optional): how many of each format. If they do not say, propose as many as are worth making.
4. Only when needed:
   - `status` → `knowledge.profiles` has more than one and none is the default: which profile the content is for.
   - `knowledge.profile.status` is `draft`: say that the content direction is a draft written from the footage, summarize it in three lines, and ask what to correct. Write the answer into the profile file (see the `knowledge-base` skill).
   - `references.found` is empty or has several folders: which folder holds the production references (graphics, sounds, reference videos). One folder found is used without asking.

Then save the answers:

```
explore.py start <project> --style fun --style technical --format short --format long [--shorts 8] [--longs 1]
                           [--profile "<name>"] [--references "<folder>"] [--notes "<anything else they asked, in their words>"]
```

Styles can be given in Portuguese (`divertido`, `técnico`, `provocativo`...); the script maps them. `start` also builds `material/` and `knowledge.md`.

| Style | In Portuguese | What it is | Works best as |
|---|---|---|---|
| `fun` | Divertido | Jokes, banter, bloopers, a funny situation with a punchline | short |
| `technical` | Técnico | A tip, an explanation or a how-to that teaches one thing | short, long |
| `vlog` | Vlog | The day or the event told in order, with behind-the-scenes | long, short |
| `provocative` | Provocativo | A strong opinion or an uncomfortable truth that invites disagreement | short |
| `story` | História | A personal story with a beginning, a turn and an outcome | short, long |
| `interview` | Entrevista | Questions and answers, or a conversation with someone interesting | short, long |
| `authority` | Autoridade | A lesson, a number or an insight that shows the speaker knows the subject | short |
| `reaction` | Reação | Answer to a comment, reaction to something that just happened or to someone's content | short |
| `promo` | Promocional | Presents a product, an offer or an invitation, with a call to action | short |
| `recap` | Resumo | The best moments of an event or a period, edited fast | short, long |

### 2. Read the direction

Read `edit/explore/knowledge.md` (people, companies, `publish` restrictions, and the content direction of the profile: audience, tone, themes, do and avoid) and `edit/context/timeline.md` (the shoot told in order). Everything proposed has to make sense for that profile.

### 3. Scout the batches

`status` → `batches` lists them. For each batch whose `notes` is not `done`, read `material/<batch>.md` and write `notes/<batch>.md`. A batch already `done` is finished work: leave it.

With more than two batches to do, give one batch to each parallel subagent, using the scout brief below. A subagent only writes its own notes file.

The notes file starts with the frontmatter printed at the top of the material file (the `material` code is how the script knows the notes match the current footage):

```markdown
---
batch: D1-05
material: m98cf999b
---

## Candidates
### Pitch ao vivo para o Felipe Titto
- format: short | styles: story, authority | strength: 9
- [0374 012.40-058.00] Igor apresenta a Ola SecretarIA do meio da plateia; [0374 061.20-079.00] a resposta do palestrante
- Why: situação rara, tensão real e desfecho; o público quer saber o que ele respondeu.
- Needs: contexto de quem é o palestrante (placa). Risk: citar o número de clientes só se estiver confirmado.

## Building blocks
- [0368 000.00-012.00] plateia aplaudindo, plano geral: abertura ou transição de vlog
- [0372 044.10-047.30] "isso aqui é ouro": frase solta para gancho

## Threads
- A promessa do pitch do dia seguinte (0327, 0336) continua em outros lotes: pode fechar um vlog.

## Not usable
- 0369: áudio do palco ininteligível.
```

- **Candidates**: a video idea that stands on footage of this batch. Give the ranges exactly as written in the material (`[<clip ref> start-end]`), the reason someone would watch, and what could go wrong.
- **Building blocks**: pieces that are not a video alone but make other videos better: establishing shots, reactions, one-liners, transitions.
- **Threads**: things that start or continue in other batches, for the planner to connect.
- Scout only for the styles and formats in the session, but note under Threads anything outstanding that falls outside them.
- A batch with nothing worth making gets a notes file that says so. Do not invent candidates to fill the file.

### 4. Plan the videos

This step is done by one agent (you), because it needs every batch at once. Read all the notes files, then:

1. **Merge and connect.** The same idea found in two batches is one video. Threads become long videos or multi-part stories. A `long` video is built from the timeline (beginning, development, payoff), with building blocks as openings and transitions.
2. **Choose.** Respect the quantity asked; when none was given, keep every idea you would defend to the user and drop the weak ones (strength below 6). Variety matters: do not propose five videos with the same hook. The same excerpt may appear in more than one video (a short and the vlog), but two shorts built on the same punchline are one video.
3. **Create each plan**: `explore.py new <project> --title "..." --format short --style fun [--style ...] --duration 35 --score 8 --person "<Name as in the knowledge base>"`. It prints the file to fill. `--duration` is the length of the finished video in seconds; `--score` is 1 to 10.
4. **Fill in every section** of the file, replacing the template text (format below).
5. `explore.py check <project>` until `to_fix` has no `problems`. It validates the clip references and time ranges against the footage, flags people marked `publish: ask` or `avoid`, rewrites `overview.md`, and lists `high_value_clips_in_no_video`: look at each of those and either use it or be able to say why not.

What makes a plan good:

- **The hook comes from the footage.** The first two seconds are a literal line or image that exists in a clip, strong without context. If the best line is in the middle, open with it and then go back.
- **One idea per short.** 20 to 60 seconds, a single point, and an ending (punchline, answer, turn). A short that needs explaining is a long video.
- **Long videos have a question** the viewer wants answered by the end ("did the pitch work?"), not just the events in order.
- **Honest ranges.** Use the times from the notes and material; the editor refines the cut on the word-level transcript, but a range that does not contain the line is a broken plan. `footage` in the overview should be about 1 to 2 times the target duration, leaving room to trim.
- **Name who appears** and what the viewer needs to know about them (a title plate), with the spelling from the knowledge base.
- **Risks are part of the plan.** Carry over the caveats of the insight files (private numbers, third parties, staged scenes presented as real) and say what to do about each: cut, blur, bleep, ask.

### 5. Present and wait

Show the user the proposals grouped by format, strongest first, each in two or three lines: ID, title, style, target duration, the hook (quoted), and the main risk if there is one. Mention where the full plans are (`edit/explore/overview.md` and `videos/`). Then ask which ones to produce and in what order.

**Nothing is produced before the user approves.** The script enforces it: a `proposed` video cannot move to `producing`.

### 6. Record the decision

| The user says | Run |
|---|---|
| "produz o V03 e o V07" | `explore.py set <project> V03 V07 --status approved --note "<their words>"` (the order given is the production order) |
| "faz o V05 primeiro" | `explore.py set <project> V05 --status approved --first` |
| "todos" | `set` with every proposed ID |
| "esse não" | `explore.py set <project> V02 --status rejected --note "<why, if they said>"` |
| "muda o V04: abre com outra frase" | edit `videos/V04-*.md`, run `check`, show the change; it stays `proposed` until approved |
| "quero mais ideias de humor" | If the style is new: `start --update` with the complete list of styles (`--style` replaces the saved list, so repeat the old ones), then step 3 again for every batch (delete the notes files first, since they were scouted without that style). If it was already in the session: step 4 again from the existing notes. Existing videos stay. |

Videos the user did not mention stay `proposed`; they can be approved later.

### 7. Produce

`status` → `videos.list` gives the order (`priority`, lowest first). Work on **one video at a time**:

1. `explore.py set <project> <ID> --status producing --workdir edit/<format>-<id>-<slug>` (for example `edit/short-v03-pitch-ao-vivo`).
2. Read `~/.claude/skills/produzir-video/SKILL.md` and follow it, with this video's plan as the request. Write its `briefing.md` inside the workdir from the plan: title, format (`short` → "Reels / Shorts direto do bruto", `long` → "Vlog / YouTube longo"), target duration, the structure with the clip ranges, hook, on-screen elements, risks to respect, the profile's content direction and visual identity from `knowledge.md`, and the references folder saved in the session (`status` → `references.chosen`). The sources are the files under `raw/` named in `## Structure`; transcripts in `edit/transcripts/` already exist.
3. When `produzir-video` delivers the file to `final/`: `explore.py set <project> <ID> --status review --final "final/<file name>"`.
4. If production stops halfway (error, missing asset, a question only the user can answer), leave the status `producing`, write what happened with `set <ID> --note "..."`, and tell the user. On resume, the video's `## Log` and its workdir say where it stopped.

**Pilot first.** The first video of each format is a pilot: after delivering it, stop, show it to the user and ask what to change in the style (subtitles, pace, plates, music) before producing the rest. Write the answer into the profile ("Formatos que funcionam", "Identidade visual") or the session notes so the next videos follow it. After the pilot is accepted, continue through the queue without stopping at each video.

### 8. Review and close

- The user accepts a video: `set <ID> --status delivered`.
- The user asks for changes: `set <ID> --status producing --note "<what to change>"`, redo it in the same workdir, deliver again.
- The user says it was posted: `set <ID> --status published --note "<where, link if given>"`.

End each session with a short report: what was delivered (with the files), what waits for review, what is still proposed, and the open doubts.

## The video file

`edit/explore/videos/<ID>-<slug>.md`, created by `explore.py new`. Change `status`, `priority`, `workdir` and `final` only through `explore.py set`, which also writes the log; edit the rest freely.

```markdown
---
id: V03
title: Fiz um pitch para o Felipe Titto no meio da palestra
format: short            # short | long
styles: [story, authority]
status: proposed         # proposed | approved | producing | review | delivered | published | rejected
priority: null           # production order, set when approved
score: 9
duration_s: 45           # target length of the finished video
profile: Igor Trindade
people: [Igor Trindade, Felipe Titto]
created: 2026-11-15
updated: 2026-11-15
workdir: null            # edit/<format>-<id>-<slug>, set when production starts
final: null              # final/<file>, set when delivered
---

## Idea
What the video is, in two or three sentences, and why this audience would watch it to the end.

## Hook
The first two seconds: the literal line or the image, and the text on screen.

## Structure
1. [0374 012.40-021.00] "Posso fazer um pitch de 30 segundos?" - gancho, corta direto para a reação da plateia
2. [0374 021.00-058.00] o pitch, enxugado para as três frases mais fortes
3. [0374 061.20-079.00] a resposta do Felipe Titto - desfecho
4. [0387 004.00-012.50] Igor contando o convite para São Paulo - fecha com a consequência

## On screen
Title plates, information plates, subtitles, inserts.

## Publishing
Title options, caption idea, call to action.

## Risks
What has to be confirmed or avoided before publishing (people, numbers, permissions).

## Log
- 2026-11-15 10:02 proposed -> approved (produz esse primeiro)
```

- Every footage piece in `## Structure` is `[<clip> start-end]` in seconds from the start of the clip, where `<clip>` is the short reference shown in the material files (`0374`) or the full clip name. Text between the pieces (narration to record, a plate) is written as a normal line without brackets.
- `people` uses the names of the knowledge base; `check` warns when one of them is marked `publish: ask` and refuses `publish: avoid`.

## Scout brief

```
You are scouting catalogued video footage for content ideas. You do not edit and you do not decide what gets made:
you write notes that a planner will read.

Read first:
  - ~/.claude/skills/content-explorer/SKILL.md, section "3. Scout the batches" (format of the notes file) and the styles table
  - <project>/edit/explore/knowledge.md   who is who, what must not be published, and the content direction (audience, tone, themes)
  - <project>/edit/context/timeline.md    the whole shoot in order, so you know where your batch fits
Then read your batch: <project>/edit/explore/material/<batch>.md

The user wants: styles <styles>; formats <formats>. <notes from the session, if any>

Write <project>/edit/explore/notes/<batch>.md, starting with the frontmatter printed at the top of the material file.
Rules:
  - Copy clip references and time ranges exactly from the material; never estimate a time that is not written there.
  - Quote lines literally. Spell names as in knowledge.md.
  - Judge by what the audience in knowledge.md would watch, not by what was important to the people filmed.
  - Carry every relevant caveat into "Risk".
  - If the batch has nothing worth making, say so in the file. Do not pad.
  - Write only that one file. Do not ask questions.
Reply with one line per candidate (working title, format, strength) and the threads you found.
```

## Updating

- **New footage** (another day catalogued by `context-extractor`): `status` answers `material:`. Run `explore.py material <project>`; batches whose clips changed become `stale` and new ones `missing`. Scout those, then plan again: add new videos and extend existing `proposed` ones (a vlog that now has its ending). Do not touch videos that are approved or beyond without telling the user what changed.
- **The knowledge base or the profile changed**: `explore.py material <project>` refreshes `knowledge.md`; run `check`, since a `publish` restriction may now affect a plan.
- **A name was corrected in the insight files**: the affected batches become `stale`. If only spellings changed, fix the same names in the notes and plans and update the `material` code in the notes frontmatter instead of scouting again.
