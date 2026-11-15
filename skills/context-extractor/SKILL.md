---
name: context-extractor
description: Turns a folder of raw video clips into structured context an editor or another skill can search - a transcript, a contact sheet and an insight file per clip (what happens, who appears, who is mentioned, quotable moments with timestamps, how usable it is), plus a chronological catalog of the whole shoot. Every person and company named in the footage is looked up in the knowledge base and researched on the web when unknown. Use it whenever the user has many clips from an event, trip, visit or recording day and wants to know what is in the footage, catalog or index it, extract insights, find the good moments, or prepare the material before deciding which videos to make - also when new footage is added to a project that was already extracted, and before content-explorer or produzir-video on a project with dozens of clips. For a plain transcript or subtitles of one video, use video-toolkit instead.
---

# Context extractor

Raw footage is opaque: nobody can plan videos from 200 files named `DJI_0324`. This skill makes the footage readable. Each clip gets a small insight file, and the whole shoot gets a catalog in recording order. Other skills (and the user) read those to decide what to produce.

It describes and locates; it does not edit and it does not propose videos. Cut points are still decided from the word-level transcript at editing time, so the timestamps written here only need to be good enough to find the moment again.

**Windows:** `PYTHONUTF8=1` (PowerShell: `$env:PYTHONUTF8="1"`). Script: `python ~/.claude/skills/context-extractor/scripts/context.py <command> <project>`. Every command prints JSON.

## Where things go

The project follows the `produzir-video` layout (`raw/` read-only, everything generated in `edit/`). A plain folder of clips also works: the output goes to `<folder>/edit/`.

```
<project>/
├── raw/                          footage, never modified (subfolders are fine)
└── edit/
    ├── transcripts/<clip>.json   word-level, shared with the editing skills (never redone)
    └── context/
        ├── inventory.json        clips in recording order, grouped into days and blocks
        ├── frames/<clip>.jpg     contact sheet, each frame labelled with its time
        ├── work/<clip>.md        worksheet: metadata, names recognized, phrase-level transcript
        ├── knowledge.md          digest of the knowledge base, rewritten by `prepare`
        ├── clips/<clip>.md       the insight file (you write this)
        ├── glossary.md           doubts about names and terms of this project only (optional)
        ├── catalog.md            one line per clip, generated
        └── timeline.md           the shoot told in order (you write this)
```

People, companies and the spelling of their names live in the knowledge base (`Base de conhecimento/`, beside the projects), which every project shares. Read `~/.claude/skills/knowledge-base/SKILL.md` before the first run: steps 2, 3 and 5 depend on it.

## Flow

Run the steps in order. `context.py status <project>` tells where a project stands at any time, so an interrupted run resumes from the first step that still has work.

1. **Prepare.** `context.py prepare <project>` probes every clip, orders them by the recording time in the file metadata, groups them into days and blocks (a block is a run of clips with no pause longer than `--gap-min`, default 10 min), transcribes through `video-toolkit`, renders the contact sheets, and writes the worksheets and `knowledge.md`. It ends by printing the status JSON.
   - Everything is cached per clip, so it is safe to run again at any time, and after new footage arrives it only processes the new clips.
   - The names in the knowledge base go into the transcription prompt, which makes the recognizer spell them right. So fill the knowledge base with what the user already told you (step 2) before the first `prepare` whenever you can.
   - The camera stores the time in UTC; it is converted with this computer's time zone. If the footage was shot in another time zone, pass `--utc-offset <hours>`.
   - `MISSING_API_KEY` (exit code 3): follow "Sem chave do Groq" in `~/.claude/skills/video-toolkit/SKILL.md`.
   - DJI proxies (`.LRF` next to the `.MP4`) are used for the frames and audio levels when present; it is much faster on large shoots.
   - `"knowledge": {"base": null}` in the status means no knowledge base was found. Ask the user once whether to create it (`kb.py init <projects root>`), then run `prepare` again.

2. **Learn who is who.** Read `edit/context/knowledge.md`, `edit/context/glossary.md` if it exists, `edit/briefing.md` if it exists, and anything the user said about who and what was filmed. Then, for everything the user said that the knowledge base lacks (who filmed, partners, companies, the event), add or update the entries as the `knowledge-base` skill describes ("When the user tells you something") and run `prepare` again so the digest and the worksheets pick it up.

3. **Research the names in the footage.** Speech recognition mangles proper names, and an insight that calls the user's company by the wrong name poisons every later step. So before writing insights:
   - Collect the names of people, companies, products and events spoken in the transcripts. Each worksheet lists, under "Names the knowledge base recognizes in this transcript", the ones that are already known; every other proper name in the transcript is a candidate. On a large shoot, have the subagents of step 4 report the unknown names instead of reading every transcript yourself, and do this step after their first pass.
   - For each candidate: `kb.py find "<name>" --from <project>`. No match: search the web and add it with `kb.py add ... --status researched`, following "Researching a name on the web" in the `knowledge-base` skill. The event's own site or Instagram (line-up, sponsors, startups) is usually the best first search, because it gives the right spelling of many names at once.
   - A wrong spelling of a known entry: add it to that entry's `heard_as`.
   - A word that is not a person or a company: add it to `termos.md` in the knowledge base.
   - A doubt that only matters to this project ("the investor in the blue shirt may be the one Igor calls João"): write it in `edit/context/glossary.md`.
   - Run `prepare` again at the end (it is instant when nothing new was filmed) to refresh `knowledge.md` and the worksheets.

4. **Write the insight files.** `status` lists the clips that still need one (`insights_missing`), grouped by block. Work block by block, because consecutive clips are usually the same scene and only make sense together.
   - With more than about 10 clips to do, hand them to parallel subagents: one batch per block, splitting blocks above ~8 clips or ~15 minutes of footage. Give each one the brief below. With fewer, write them yourself.
   - A file that already exists is finished work. Leave it alone unless the user asks to redo it.
   - Subagents answer with the names they could not resolve. Run step 3 for those names.

5. **Fix the names.** `context.py labels <project>` (nothing is written without `--apply`) lists:
   - `rename`: names in `people` and `mentions` that the knowledge base knows under another spelling, with the name they will get. Check the list, then run it again with `--apply`.
   - `names_not_in_knowledge_base`: names no entry has. Research them (step 3), or leave them if they are people who only pass by.
   - `inferred`: people identified by deduction ("João Torrezani (presumed; beige BOSS t-shirt)"). Keep the note until the user confirms.
   - A person who was only described and whose name you learned later: `context.py labels <project> --set "young bearded man in beige t-shirt=João Torrezani" --apply`. The left side is the label exactly as written in the files; repeat `--set` for each label.
   - `status` → `knowledge.misspellings` lists wrong spellings still written in the prose of the insight files and the timeline, with the files. Fix them by editing each file, replacing only the wrong word (a quote keeps what was said, with the name spelled right).

6. **Check and build the catalog.** `context.py catalog <project>` refuses to write while any clip lacks a valid insight file and says which; fix those and run it again.

7. **Write `timeline.md`** from the catalog: for each day and block, a short paragraph on what happened, who was there, and the strongest material in it. Then a closing section on the threads that run across blocks (a person followed all day, a story that starts in the morning and pays off at night, recurring jokes). This is the first file a planner reads, so write it for someone who was not there, with every name spelled as in the knowledge base.

8. **Report**, in the user's language:
   - clips and minutes per day, how the value splits, and the handful of strongest clips;
   - what was added to the knowledge base from the web (`kb.py check` → `awaiting_confirmation`), asking the user to confirm or correct it in one go;
   - recurring people nobody could name (with the clip and time where they are best seen), names that stayed in doubt, clips with unusable audio.
   When the user answers, update the knowledge base, run `labels --apply` (with `--set` where needed), fix the prose of the affected files, and rebuild the catalog.

## The insight file

`edit/context/clips/<clip>.md`. The worksheet has the first six frontmatter fields ready to copy. Keys and the fixed values are in English; write the prose and the quotes in the language spoken in the footage.

```markdown
---
clip: DJI_20261113162211_0324_D
file: raw/DJI_20261113162211_0324_D.MP4
recorded_at: 2026-11-13T15:22
block: D1-B01
duration_s: 72.47
orientation: vertical
type: conversation
value: high
audio: fair
image: good
people: [Igor Trindade, "João Torrezani (presumed; beige BOSS t-shirt, backpack)", "man in navy event shirt with headset"]
mentions: [Ola SecretarIA, HotSeller, Divinópolis Summit]
topics: [chegada no evento, startups de Divinópolis]
summary: Chegada ao pavilhão; brincadeira com um organizador sobre o próximo unicórnio sair de Divinópolis.
---

## What happens
Two or three sentences: where it is, who is there, what they do and say, how it ends.

## Moments
- [000.00-013.50] "O próximo unicórnio do Brasil vai sair de Divinópolis." Opening energy, works as a hook; said to camera.
- [028.50-036.90] (visual) wide pan of the main stage and audience, steady. B-roll.

## Continuity
Same scene continues in 0325. The line at 020.34 repeats the one at 012.36 (transcription echo, not a retake).

## Caveats
Swearing at 051. Third party mentions how many paid accounts his company has (058-072): check before publishing.
```

- The frontmatter must be valid YAML: put any value that contains a colon, a quote or a `#` inside quotes (a `summary` with "he says: ..." breaks the file otherwise). `status` and `catalog` report the files that fail.
- **type**: `talk` (someone presenting to an audience), `to-camera` (speaking to the lens), `interview` (questions and answers), `conversation` (people talking among themselves), `b-roll` (images that matter more than the sound), `behind-the-scenes`, `screen`, `discard` (accidental recording, pocket footage, nothing usable).
- **value**: how much a video would lose without this clip. `high` carries a video or a strong moment on its own; `medium` is solid supporting material; `low` is usable filler; `none` goes with `discard`. Judge the content first, then the technical quality: a great line with rough audio is still worth more than a clean shot of nothing. Funny, spontaneous and personal moments count as content, not as noise.
- **audio** and **image**: `good`, `fair` or `poor`, from the levels in the worksheet, how coherent the transcript is, and the contact sheet.
- **people**: who is seen or heard in the clip, one label per person:
  - known for sure (they say their name, someone calls them by it, or the knowledge base describes them unmistakably): the name exactly as in `knowledge.md`, e.g. `Igor Trindade`;
  - deduced (appearance or context matches an entry, but nothing in this clip proves it): the name plus a note that starts with `presumed`, e.g. `"João Torrezani (presumed; beige BOSS t-shirt, backpack)"`;
  - named in the footage but absent from the knowledge base: the name as heard, e.g. `Silmara`;
  - nobody named them: a short description that starts with a lowercase letter (clothing, role), reused word for word across the clips of the block so the same person can be traced, e.g. `"man in navy event shirt with headset"`.
- **mentions**: people, companies, products and events that are talked about but not on screen, spelled as in `knowledge.md`. This is how a planner finds every clip where a company is cited. Leave out generic words (a city, "o governo").
- **Moments** are the reason this file exists. Each one is a range from the worksheet, the literal words (or what is seen, for visual moments), and why an editor would want it: hook, punchline, clear explanation, emotion, a number, a good image. Prefer five real ones to fifteen weak ones, and write none when the clip has none. Quote what was said, but spell names as in `knowledge.md`.
- **Continuity**: what the neighbouring clips have to do with this one (same scene, retake, answer to a question asked in the previous clip).
- **Caveats**: anything that could embarrass someone or cause trouble if published (private data, prices, third parties who did not agree to be filmed, off-the-record remarks), any entry marked `[publish: ask]` or `[publish: avoid]` in `knowledge.md` that appears or is mentioned, and any doubt about the transcript or about who someone is.

Describe only what the transcript and the frames show. Use the knowledge base to spell and identify, never to add facts the clip does not contain: if `knowledge.md` says someone is an investor but the clip only shows him ordering coffee, the insight says he orders coffee. In noisy places the recognizer invents repeated phrases and collapses timestamps (several lines a fraction of a second long, one after another); say so in Caveats instead of treating that text as speech. A clip whose frames show nothing recognizable and whose transcript is empty is `discard`, not a guess.

## Subagent brief

Each subagent starts with no context, so the brief has to carry everything. Fill in the paths, the clip list and the context:

```
You are cataloguing raw video footage so an editor can find material later. Write one insight file per clip.

Clips (one block of the shoot, in recording order): <clip names>

Read first:
  - ~/.claude/skills/context-extractor/SKILL.md, section "The insight file" (format and rules; follow it exactly)
  - <project>/edit/context/knowledge.md   who is who and how every name is spelled
  - <project>/edit/context/glossary.md    if it exists: open doubts about this project
For each clip read:
  - <project>/edit/context/work/<clip>.md    metadata, the names already recognized, the transcript with time ranges
  - <project>/edit/context/frames/<clip>.jpg contact sheet; look at it, every frame is labelled with its time
Context from the user: <who filmed, what the event is, what the people likely to appear wear in this shoot>

Rules:
  - Read all the clips of the batch before writing, because consecutive clips are often one scene.
  - Names: use the exact spelling in bold in knowledge.md. The transcript often misspells them; the worksheet
    section "Names the knowledge base recognizes" gives the right form. Never copy a misspelling into the file.
  - Identify a person by name only when the clip proves it or knowledge.md describes them unmistakably.
    Otherwise write the name with a note starting with "presumed", or a description starting with a lowercase letter.
  - Write each file to <project>/edit/context/clips/<clip>.md. Do not modify anything else, and never touch raw/.
  - Do not ask questions; when something is unclear, write the doubt under Caveats.

Reply with:
  1. one line per clip: clip, type, value;
  2. names of people, companies, products or events heard in these clips that are NOT in knowledge.md
     (as heard, with the clip and the time, and what the context says about them);
  3. people who appear in several clips and whom you could not name (your description, clips).
```

## Starting over and updating

- **New footage** (another day downloaded, more clips copied in): run `prepare` again and continue from step 3. Existing insight files stay; the catalog and the timeline are rebuilt. Blocks are numbered within each day, so a later day does not renumber the earlier ones.
- **The knowledge base changed** (the user confirmed a name, fixed a spelling): `prepare` (refreshes the digest and worksheets), then step 5. Insight files are corrected in place, not rewritten.
- **Redo one clip**: delete its file in `clips/` and run the flow again. Delete the transcript too only if the audio itself was wrong; it is shared with the editing skills.
- **Redo everything**: confirm with the user first, naming what will be lost (how many insight files, plus the timeline). Then remove `edit/context/clips/`, `catalog.md` and `timeline.md`. Keep the transcripts and frames, which are deterministic and expensive.
- Renaming or moving clips inside `raw/` after extraction breaks the link to their transcripts and insights, which are keyed by file name.
