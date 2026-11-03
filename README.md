# video-skills-box

Skills de vídeo para o Claude Code (e agentes compatíveis) e os assets compartilhados entre elas.

## Estrutura

```
skills/
├── video-toolkit/            ← compartilhado por todas as skills
│   ├── SKILL.md              ← transcrição avulsa + referência das ferramentas
│   ├── scripts/transcribe.py ← CLI de transcrição (Groq via mediacript → Whisper local)
│   ├── videokit/             ← pacote Python comum (ffmpeg/ffprobe, transcrição, formato Scribe)
│   └── assets/               ← fontes, logos, músicas, sfx, LUTs, overlays
├── editar-video-youtube/     ← bruto → final.mp4 (camada de preferências sobre a video-use)
├── cortes-verticais/         ← final.mp4 → shorts 9:16
│   └── scripts/              ← make_short.py, remap_transcript.py
└── referencia-de-estilo/     ← vídeo de referência → estilo.md + comparação de métricas
    ├── scripts/analyze_video.py
    └── estilos/              ← estilos salvos para reuso
```

Regras para manter o repositório organizado:

- **Uma skill = uma pasta em `skills/`** com `SKILL.md` e, se precisar, `scripts/`, `references/`, `estilos/` etc. Só o que é específico daquela skill.
- **Código usado por mais de uma skill vai para `skills/video-toolkit/videokit/`.** Scripts de skill importam assim:
  ```python
  sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))
  from videokit.media import probe, run
  ```
  Funciona no repositório e instalado em `~/.claude/skills`, porque as skills ficam sempre lado a lado.
- **Assets compartilhados em `skills/video-toolkit/assets/`** (convenções em `assets/README.md`). O toolkit é uma skill para que os assets e o código sejam instalados junto com as outras.
- Nos `SKILL.md`, referencie caminhos instalados (`~/.claude/skills/<skill>/...`).

## Instalação

As skills são ligadas (junction no Windows, symlink no macOS/Linux) em `~/.claude/skills`, então o repositório é a única cópia: editar aqui já vale para o Claude.

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1   # Windows
```
```sh
./install.sh                                            # macOS/Linux
```

Se já houver uma pasta de skill com o mesmo nome, ela é movida para `~/.claude/skills/.trash/` antes de ligar. Rode de novo ao criar uma skill nova.

## Dependências

- Python ≥ 3.10: `pip install -r requirements.txt`
- `ffmpeg`/`ffprobe` e `node` no PATH
- [video-use](https://github.com/browser-use/video-use) clonada em `~/.claude/skills/video-use` (`pack_transcripts.py`, `timeline_view.py`, `render.py`). É de terceiros (MIT) e não é copiada para cá.
- [mediacript](https://github.com/igortrinidad/mediacript) em `~/code/mediacript` (ou defina `MEDIACRIPT_CLI` com o caminho do `cli.mjs`) com a chave Groq configurada. Sem ele a transcrição cai para o Whisper local.
