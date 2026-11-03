---
name: video-toolkit
description: Ferramentas compartilhadas pelas skills de vídeo (editar-video-youtube, cortes-verticais, referencia-de-estilo) — transcrição rápida via mediacript/Groq com Whisper local de reserva, no formato JSON da Scribe usado pela video-use, e assets comuns (fontes, logos, músicas, LUTs). Use quando o usuário pedir só para transcrever vídeos/áudios ou gerar legendas com timestamps de palavra, ou quando outra skill de vídeo mandar usar estas ferramentas.
---

# Video toolkit (compartilhado)

Código e assets usados por todas as skills de vídeo. As outras skills chamam os scripts daqui; não copie esta lógica para dentro delas.

**Windows:** `PYTHONUTF8=1` (em PowerShell, `$env:PYTHONUTF8="1"`).

## Transcrição

```
python ~/.claude/skills/video-toolkit/scripts/transcribe.py <pasta_ou_video> --edit-dir <edit> --language pt
```

- Saída: `<edit>/transcripts/<nome>.json`, formato Scribe (`words[]` com `type` word|spacing, `start`, `end`, `text`, `speaker_id`). `pack_transcripts.py`, `timeline_view.py` e `render.py` da video-use leem direto.
- `--engine auto` (padrão): mediacript na nuvem (Groq whisper-large-v3, 3 arquivos em paralelo; ~1 min para 57 min de fala). O que falhar (sem rede, sem chave/cota) cai sozinho para o Whisper local (`--whisper-model small`, CPU, lento). `--engine whisper` força só local; `--engine mediacript` falha em vez de cair.
- O áudio vai em pedaços de no máximo 10 MB cortados em pausas, e trechos com som que voltaram vazios são reenviados.
- O prompt padrão (`--prompt`) mantém muletas ("é", "né", "tipo") e "pato amarelo" escritos literalmente. `--prompt ""` desliga.
- Cache por arquivo: transcrição existente nunca é refeita (apague o JSON para refazer).
- Precisa de `node` e `ffmpeg` no PATH e da chave Groq na config do mediacript. O CLI fica em `~/code/mediacript/packages/cli/cli.mjs`; se estiver em outro lugar, defina `MEDIACRIPT_CLI`.

## Assets

`~/.claude/skills/video-toolkit/assets/` — veja `assets/README.md` para as pastas e convenções.

## Código compartilhado (para quem escreve scripts de skill)

Pacote `videokit/` (importe com `sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))` a partir de `skills/<skill>/scripts/`):

- `videokit.media`: `VIDEO_EXTS`, `MEDIA_EXTS`, `list_media`, `run`, `capture`, `probe`, `probe_fps`, `extract_audio`, `srt_ts`.
- `videokit.transcript`: `DEFAULT_PROMPT`, `scribe_words`, `write_transcript`, `load_words`, `transcript_path`, `count_words`.
- `videokit.transcribe.transcribe_all`: pipeline mediacript → Whisper local.
