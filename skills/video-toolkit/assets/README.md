# Assets compartilhados

Arquivos usados em vários vídeos e por várias skills. Referencie sempre pelo caminho instalado
(`~/.claude/skills/video-toolkit/assets/...`) ou, em Python, por `videokit.ASSETS_DIR`.

| Pasta | Conteúdo |
|---|---|
| `fonts/` | Fontes de legenda e títulos (`.ttf`/`.otf`) |
| `logos/` | Logos e marcas d'água (PNG com transparência) |
| `music/` | Trilhas e vinhetas com licença de uso |
| `sfx/` | Efeitos sonoros curtos |
| `luts/` | LUTs de cor (`.cube`) |
| `overlays/` | Molduras, lower thirds, cartões de abertura/encerramento |

Convenções:

- Nomes em minúsculas com hífen: `logo-canal-branco.png`, `trilha-intro-calma.mp3`.
- Para música/fonte de terceiros, registre a origem e a licença em `CREDITS.md` nesta pasta.
- Arquivos grandes (vídeo, áudio > ~20 MB) devem ir no Git LFS (veja `.gitattributes` na raiz do repositório).
