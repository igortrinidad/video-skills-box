---
name: video-toolkit
description: Ferramentas compartilhadas pelas skills de vídeo (produzir-video, editar-video-youtube, cortes-verticais, referencia-de-estilo, video-to-code) — transcrição rápida via mediacript/Groq com Whisper local de reserva, no formato JSON da Scribe usado pela video-use, e assets comuns (fontes, logos, músicas, LUTs). Use quando o usuário pedir só para transcrever vídeos/áudios ou gerar legendas com timestamps de palavra, ou quando outra skill de vídeo mandar usar estas ferramentas.
---

# Video toolkit (compartilhado)

Código e assets usados por todas as skills de vídeo. As outras skills chamam os scripts daqui; não copie esta lógica para dentro delas.

**Windows:** `PYTHONUTF8=1` (em PowerShell, `$env:PYTHONUTF8="1"`).

## Transcrição

```
python ~/.claude/skills/video-toolkit/scripts/transcribe.py <pasta_ou_video> --edit-dir <edit> --language pt
```

- Saída: `<edit>/transcripts/<nome>.json`, formato Scribe (`words[]` com `type` word|spacing, `start`, `end`, `text`, `speaker_id`). `pack_transcripts.py`, `timeline_view.py` e `render.py` da video-use leem direto.
- `--engine auto` (padrão): mediacript na nuvem (Groq whisper-large-v3, 3 arquivos em paralelo; ~1 min para 57 min de fala). O que falhar (sem rede, cota, erro do provedor) cai sozinho para o Whisper local (`--whisper-model small`, CPU, lento). `--engine whisper` força só local; `--engine mediacript` falha em vez de cair.
- O áudio vai em pedaços de no máximo 10 MB cortados em pausas, e trechos com som que voltaram vazios são reenviados.
- O prompt padrão (`--prompt`) mantém muletas ("é", "né", "tipo") e "pato amarelo" escritos literalmente. `--prompt ""` desliga.
- Cache por arquivo: transcrição existente nunca é refeita (apague o JSON para refazer).
- Precisa de `node` e `ffmpeg` no PATH. O mediacript roda via `npx mediacript@^1.2.42` (baixado e guardado em cache no primeiro uso). Se existir o clone em `~/code/mediacript/packages/cli/cli.mjs`, ele tem prioridade (útil para testar mudanças não publicadas); `MEDIACRIPT_CLI=<caminho do cli.mjs>` força outro.

### Sem chave do Groq (saída `MISSING_API_KEY`, código 3)

Se o script parar com `MISSING_API_KEY`, nada foi transcrito e ele **não** caiu para o Whisper local (de propósito: o local leva ~1h por hora de vídeo). Não tente adivinhar nem procurar chaves no computador. Pare e pergunte ao usuário, numa única mensagem:

> Para transcrever rápido preciso de uma chave do Groq (tem plano gratuito). Crie em https://console.groq.com/keys → **Create API Key** e cole aqui. Se preferir, transcrevo localmente com o Whisper, sem chave, mas leva cerca de 1 hora por hora de vídeo.

- Se o usuário colar a chave: salve com
  `python ~/.claude/skills/video-toolkit/scripts/mediacript_key.py set groq <chave>`
  (a chave é validada no Groq antes de salvar; código 1 = rejeitada → peça outra). Depois rode a transcrição de novo. Não repita a chave nas respostas nem a grave em arquivos do projeto.
- Se preferir local: rode de novo com `--engine whisper` (em segundo plano se for longo).
- Para conferir sem transcrever: `python ~/.claude/skills/video-toolkit/scripts/mediacript_key.py status` (`transcriptionReady`).
- Alternativa sem salvar: variável de ambiente `GROQ_API_KEY`.

## Assets

`~/.claude/skills/video-toolkit/assets/` — veja `assets/README.md` para as pastas e convenções. São assets técnicos (fontes, LUTs). Os assets de produção do usuário (elementos gráficos, sons, motions, vídeos de referência) ficam na pasta `Referencias gerais/` da raiz de projetos — veja a skill `produzir-video`; eles têm prioridade.

## Código compartilhado (para quem escreve scripts de skill)

Pacote `videokit/` (importe com `sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))` a partir de `skills/<skill>/scripts/`):

- `videokit.media`: `VIDEO_EXTS`, `MEDIA_EXTS`, `list_media`, `run`, `capture`, `probe`, `probe_fps`, `extract_audio`, `srt_ts`.
- `videokit.transcript`: `DEFAULT_PROMPT`, `scribe_words`, `write_transcript`, `load_words`, `transcript_path`, `count_words`.
- `videokit.transcribe.transcribe_all`: pipeline mediacript → Whisper local (levanta `MissingKeyError` sem chave).
- `videokit.cli.run_main(main)`: use no `if __name__ == "__main__"` de scripts que transcrevem, para sair com código 3 e a mensagem `MISSING_API_KEY` em vez de um traceback.
