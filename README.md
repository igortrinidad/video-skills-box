# video-skills-box

Skills de vídeo para o Claude Code (e agentes compatíveis) e os assets compartilhados entre elas.

## Estrutura

```
skills/
├── video-toolkit/            ← compartilhado por todas as skills
│   ├── SKILL.md              ← transcrição avulsa + referência das ferramentas
│   ├── scripts/transcribe.py ← CLI de transcrição (Groq via mediacript → Whisper local)
│   ├── videokit/             ← pacote Python comum (ffmpeg/ffprobe, transcrição, formato Scribe, pastas de projeto, base de conhecimento)
│   └── assets/               ← fontes, logos, músicas, sfx, LUTs, overlays
├── produzir-video/           ← porta de entrada: raiz de projetos, Referências gerais, tipo de vídeo, entrega em final/
│   └── scripts/projeto.py    ← raiz / scan / init / entregar
├── knowledge-base/           ← pessoas, empresas e perfis de conteúdo, compartilhados por todos os projetos
│   └── scripts/kb.py         ← where / init / find / add / check / digest
├── context-extractor/        ← pasta de clips brutos → insight por clip + catálogo cronológico (edit/context/)
│   └── scripts/context.py    ← prepare / status / labels / catalog
├── content-explorer/         ← material catalogado → vídeos propostos, aprovação, fila de produção e status (edit/explore/)
│   └── scripts/explore.py    ← status / start / material / new / check / set / reset
├── editar-video-youtube/     ← bruto → final.mp4 (camada de preferências sobre a video-use)
├── cortes-verticais/         ← final.mp4 → shorts 9:16
│   └── scripts/              ← make_short.py, remap_transcript.py
├── referencia-de-estilo/     ← vídeo de referência → estilo.md + comparação de métricas
│   ├── scripts/analyze_video.py
│   └── estilos/              ← estilos salvos para reuso
└── video-to-code/            ← link do YouTube → código transcrito da tela + README com prints
    └── scripts/video_to_code.py  ← destino / baixar / frames / transcrever / frame / crop
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
- Skills novas são escritas em inglês (nome, `SKILL.md`, scripts) e conversam com o usuário na língua dele. O que precisa ser decidido sempre do mesmo jeito (estado, validação, nomes de arquivo) fica no script, que responde em JSON com um campo `next`; assim modelos menores conseguem seguir o fluxo.

## Do material bruto aos vídeos

```
knowledge-base ──┐  quem é quem, grafia dos nomes, direção de conteúdo do perfil
                 ▼
raw/ ─► context-extractor ─► content-explorer ─► produzir-video ─► final/
        o que há em cada      quais vídeos fazer;   edita um vídeo
        clip (edit/context)   espera aprovação      (editar-video-youtube,
                              (edit/explore)         cortes-verticais)
```

Cada etapa grava o que fez no projeto e pode ser retomada: `context.py status` e `explore.py status` dizem onde parou.

## Pasta de projetos (onde ficam os vídeos)

```
<raiz>/                         ← perguntada pela produzir-video; a última fica em ~/.config/video-skills/config.json
├── Referencias gerais/
│   ├── Elementos graficos gerais/   ← o nome do arquivo descreve quando usar
│   ├── Videos de referencia/<Tipo>/<Nome>/   ← + estilo.md gerado
│   ├── Assets/                      ← logos, imagens, prints usados em vários vídeos
│   ├── Sons/
│   └── Motions/
├── Base de conhecimento/            ← editável à mão; criada com `kb.py init <raiz>`
│   ├── pessoas/  empresas/          ← uma ficha .md por pessoa / empresa, produto, evento
│   ├── perfis/                      ← direção de conteúdo de cada perfil
│   └── termos.md                    ← outras palavras que a transcrição erra
└── <Projeto>/
    ├── raw/      ← bruto (somente leitura)
    ├── assets/   ← imagens, prints, logos deste projeto (somente leitura)
    ├── refs/     ← opcional
    ├── edit/     ← tudo o que é gerado
    │   ├── transcripts/   ← transcrições por palavra, compartilhadas
    │   ├── context/       ← context-extractor: clips/<clip>.md, catalog.md, timeline.md
    │   └── explore/       ← content-explorer: videos/<ID>-<slug>.md (plano + status), overview.md
    └── final/    ← "AAAA-MM-DD_HHMM - Título.mp4"
```

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
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (instalado pelo `requirements.txt`), usado pela `video-to-code` para baixar do YouTube. Mantenha atualizado (`pip install -U yt-dlp`): o YouTube muda com frequência.
- [video-use](https://github.com/browser-use/video-use) clonada em `~/.claude/skills/video-use` (`pack_transcripts.py`, `timeline_view.py`, `render.py`). É de terceiros (MIT) e não é copiada para cá.
- [SFX Kit](https://github.com/wyzowl/sfx-kit) (CC0), efeitos sonoros usados pela `produzir-video`: clonado sob demanda em `~/.cache/video-skills/sfx-kit` (~67 MB), fora do repositório.
- [mediacript](https://www.npmjs.com/package/mediacript) ≥ 1.2.42, usado via `npx mediacript@^1.2.42` (sem instalar nada), com uma chave do Groq ([console.groq.com/keys](https://console.groq.com/keys)):
  `python skills/video-toolkit/scripts/mediacript_key.py set groq <chave>` ou a variável `GROQ_API_KEY`. Sem chave, os scripts param com `MISSING_API_KEY` (código 3) e o Claude pede a chave; `--engine whisper` transcreve localmente sem chave.
  - Ordem de resolução: `MEDIACRIPT_CLI` (caminho de um `cli.mjs`) → clone local em `~/code/mediacript/packages/cli/cli.mjs` (para desenvolver o mediacript) → `npx`.
  - Ao publicar uma versão do mediacript que mude o comando `transcribe`, atualize `MIN_VERSION` em `skills/video-toolkit/videokit/mediacript.py`.
