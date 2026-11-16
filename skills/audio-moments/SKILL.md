---
name: audio-moments
description: Finds the emotional peaks of raw footage by listening to the sound, not just reading the transcript - applause, cheering, shouting, laughter, crying, a crowd reacting, chants, celebrations, the moment a winner is announced - and ranks them across a whole project with the words said right before and during each one. Runs locally (a sound-event model plus loudness plus how the transcript was spoken), free, about 1 minute per 15 minutes of footage on CPU. Use it whenever the user wants the exciting, emotional, celebratory or funny moments of a shoot, event, talk or vlog ("momentos de palmas", "quando o público vibrou", "a comemoração", "as risadas", "os momentos emocionantes", "a transcrição está deixando passar momentos"), wants hooks or highlights for shorts and reels, or before content-explorer, cortes-verticais or produzir-video on an event with an audience. Also when context-extractor is cataloguing footage of an event, to enrich the Moments of each clip.
---

# Audio moments

A transcript keeps the words and loses the room: the applause after a line, the crowd screaming when a name is announced, a burst of laughter, someone shouting "AAAAH!". Those are often the best seconds of an event, and an agent reading only text walks right past them. This skill listens for them.

It finds and ranks; it does not cut. The times are good enough to locate the moment; the exact cut points still come from the word-level transcript at editing time.

**Windows:** `PYTHONUTF8=1` (PowerShell: `$env:PYTHONUTF8="1"`). Script: `python ~/.claude/skills/audio-moments/scripts/moments.py <command> <project|file>`. Every command prints JSON.

## How it hears

Three independent signals, combined per moment:

| signal | from | catches |
|---|---|---|
| `applause`, `cheering`, `laughter`, `crying`, `crowd` | PANNs Cnn14, a sound model trained on AudioSet (527 sound classes), every 0.25 s | the audience: clapping, whoops, screams, laughs, a crowd roaring |
| `loud` | loudness, against the usual speaking level of the clip and of the whole project | someone yelling, a room exploding, the person filming getting excited |
| `shout`, `words` | the transcript, if it exists | "AAAAAH!", "Uuuuu", chants ("Ola! Ola! Ola!"), "parabéns", "conseguimos", "que massa" |

A moment where two or three signals agree is almost always real and scores higher. A single weak signal (a lone "obrigado", one loud second) is scored down. The score goes from 0 to 1; the report keeps moments at 0.4 or more.

Know its limits so you can judge the results:
- In handheld footage the voice next to the camera drowns the room. The sound model may give a real crowd cheer only 0.1-0.2, so it is tuned to be sensitive and the other two signals confirm it.
- It hears **intensity**, not *which* emotion. A shout of joy and a shout of anger look the same. The words around the moment tell you which. It does not catch quiet emotion either (a voice breaking, a long silence after a confession); for those the transcript is still the guide.
- Music under the audio and wind on the microphone produce false `loud` peaks. Clips with music throughout are marked `(over music)`.

## Flow

1. **Set up, once.** `moments.py setup` downloads the model (~330 MB, to `~/panns_data/`). Needs `pip install panns-inference torch` and `ffmpeg`. Nothing is sent to the cloud.
2. **Transcribe first when you can.** The `shout` and `words` signals and the quotes in the report come from `edit/transcripts/<clip>.json`. If the project went through `context-extractor`, they already exist. If not, and the user wants the words too, run `video-toolkit`'s transcription first (never transcribe yourself). Without transcripts the skill still works on sound alone, and `without_transcript` in the output lists the clips that would gain from one.
3. **Scan.** `moments.py scan <project>` analyses every clip that is not cached yet and writes the report. A single file also works: `moments.py scan <file.mp4>`.
   - It follows `edit/context/inventory.json` when it exists (recording order, DJI `.LRF` proxies, which are much faster), else it reads `raw/` (or the folder itself).
   - About 1 minute of processing per 15 minutes of footage on CPU with `--jobs 2`. On a long shoot, run it in the background and say how long it will take.
   - The cache is per clip: new footage only processes the new clips. Detection runs from the cache, so `moments.py report <project> --min-score 0.3` rebuilds the report with another threshold in seconds.
4. **Check before you claim.** Read `edit/moments/moments.md`. For each moment you intend to use or report:
   - read `said before` and `said during`: they tell why the room reacted (the line that got applause, the name that was announced, the joke);
   - if the project has `edit/context/clips/<clip>.md` or a contact sheet in `edit/context/frames/`, check that the picture agrees;
   - a moment whose only signal is `loud` with no words around it is often wind, a passing car or the camera being handled. Drop it unless something else supports it.
5. **Report** in the user's language: the strongest moments first, each with the clip, the time (m:ss), what happens and why it is strong ("plateia aplaude a frase X", "anúncio do primeiro lugar, grito e coro de 'Ola!'"). Group repeated hits of the same scene into one. Say what the skill cannot hear, if it matters for what the user asked.

## Output

```
<project>/edit/moments/
├── clips/<clip>.json   curves every 0.25 s per clip (cache; delete to redo one clip, or use --redo)
├── moments.md          the ranked table, for you and the user
└── moments.json        the same, for scripts: clip, file, block, recorded_at, start, end, score,
                        signals, scene, shouted, said_before, said_during
```

## With the other skills

- **context-extractor**: when cataloguing an event, run `scan` after `prepare`, and give the insight-writing subagents the rows of `moments.md` for their clips. Each strong moment belongs in the clip's `## Moments` with its range and the reason (`(sound) applause after ...`), and is a reason to raise the clip's `value`. The words alone often missed it.
- **content-explorer**: the top of `moments.md` is a list of hooks and climaxes. A short that opens or ends on a top-scored moment usually works; a recap of an event can be built around the five strongest.
- **cortes-verticais / produzir-video**: use the range to find the moment, then cut on the word-level transcript as usual. Keep a little of what was `said before`: applause without the line that caused it means nothing.
