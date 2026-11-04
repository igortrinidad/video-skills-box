---
name: editar-video-youtube
description: Edita vídeos brutos (gravações longas de YouTube, aulas, tutoriais, talking-head com ou sem tela) de ponta a ponta usando a skill video-use com transcrição rápida via mediacript (Groq), com Whisper local de reserva. Corta silêncios, erros, retakes, redundâncias e trechos com a palavra-chave "pato amarelo", alterna layout entre cara cheia e cara+tela, e entrega final.mp4 sem precisar de supervisão. Use sempre que o usuário mandar um vídeo bruto ou uma pasta de gravações e pedir para editar, limpar, cortar silêncio/erros, "deixar pronto pro YouTube", ou mencionar pato amarelo — mesmo sem citar esta skill.
---

# Editar vídeo bruto → final.mp4

Edição minimalista: o objetivo é um vídeo enxuto e natural, sem efeitos. Corta o que atrapalha (silêncio, erro, repetição, espera) e escolhe o enquadramento certo para cada momento. Nada além disso, a menos que o usuário peça.

Esta skill é uma **camada de preferências** sobre a `video-use`. Leia `~/.claude/skills/video-use/SKILL.md` e respeite as Hard Rules dela (cortes em fronteira de palavra, padding, fades de 30ms, extract por segmento → concat). Aqui ficam só as decisões editoriais do usuário e as diferenças de setup.

## Pastas

Quando o pedido vier por uma pasta raiz de projetos ("gera um vlog da pasta X"), quem organiza é a skill `produzir-video` (raiz, Referências gerais, briefing, tipo de vídeo, entrega). Layout de um projeto:

```
<Projeto>/
├── raw/     ← brutos, somente leitura (aceite material_bruto/ ou mídia solta em projetos antigos)
├── assets/  ← imagens, prints, logos do projeto para inserts (somente leitura)
├── refs/    ← referências do projeto (opcional)
├── edit/    ← tudo o que for gerado: transcripts/, edl.json, analise.md, preview.mp4, final.mp4…
└── final/   ← entregáveis: "AAAA-MM-DD_HHMM - Título.mp4"
```

- Use sempre `--edit-dir <Projeto>/edit` (não `raw/edit`). No `edl.json`, as fontes ficam relativas a `edit/`: `"../raw/ARQ.MP4"`.
- `timeline_view.py` não acha a transcrição sozinho com os brutos em `raw/`: passe `--transcript <edit>/transcripts/<nome>.json -o <edit>/verify/<png>`.
- Ao terminar, entregue o `edit/final.mp4` em `final/` com `python ~/.claude/skills/produzir-video/scripts/projeto.py entregar <edit>/final.mp4 --projeto <Projeto> --titulo "<título>"` (use `--copiar` se os `cortes-verticais` vierem em seguida). Se o usuário mandar só uma pasta solta de brutos, sem projeto, mantenha o comportamento antigo (`<pasta>/edit/final.mp4`).

## Diferenças em relação à video-use

- **Transcrição via mediacript (Groq whisper-large-v3 na nuvem)**, não ElevenLabs, usando a skill compartilhada `video-toolkit`:
  `python ~/.claude/skills/video-toolkit/scripts/transcribe.py <pasta_ou_video> --edit-dir <edit> --language pt`
  Gera JSON no mesmo formato da Scribe em `edit/transcripts/`, então `pack_transcripts.py`, `timeline_view.py` e `render.py` funcionam normalmente. É rápido: uma palestra de 57 min leva cerca de 1 min, e uma pasta com ~1h40 de material leva ~1,5 min (3 arquivos em paralelo). Não precisa rodar em segundo plano. O áudio vai em pedaços de no máximo 10 MB, cortados em pausas, e trechos com som que voltaram sem palavras são reenviados automaticamente. O prompt padrão mantém muletas ("é", "né", "tipo") e "pato amarelo" escritos literalmente. Se o mediacript falhar (sem rede, cota), o script cai sozinho para o Whisper local (modelo `small`, CPU, lento). Para forçar só local, use `--engine whisper`. **Sem chave do Groq** o script para com `MISSING_API_KEY` (código 3): siga a seção "Sem chave do Groq" de `~/.claude/skills/video-toolkit/SKILL.md` (pergunte a chave ao usuário uma vez e continue sozinho depois). Com 2 arquivos sincronizados, transcreva **só um** (o áudio é o mesmo). Cache por arquivo: nunca retranscreva.
- **Windows**: rode os helpers com `PYTHONUTF8=1` (já definido nas variáveis do usuário; em PowerShell, `$env:PYTHONUTF8="1"` se precisar) para evitar erro de encoding. Escreva `edl.json` com o tool de escrita de arquivos ou `[IO.File]::WriteAllText` — `Set-Content`/`Out-File` do PowerShell adicionam BOM e o `render.py` quebra.
- Whisper não marca eventos de áudio nem diariza (tudo é `S0`), e os timestamps podem derivar um pouco mais que a Scribe (no Groq, o início das palavras fica a ±0,1s do Whisper local). Por isso use padding no lado mais folgado da janela (≈80ms antes, ≈120ms depois) e confira com `timeline_view` nos cortes duvidosos. Às vezes uma palavra vem "esticada" por segundos sobre uma pausa: não confie no `end` de uma palavra com duração > 1,5s, corte pelo início da palavra seguinte.
- **Não espere confirmação da estratégia quando o material for claro.** O usuário quer mandar o bruto e receber o final pronto ("posso ir dormir?"). Só pergunte se houver ambiguidade real (ex.: não dá pra saber qual arquivo é cara e qual é tela, ou há dois takes completos concorrentes). Nesse caso pergunte tudo de uma vez, numa única mensagem, e depois siga sozinho até o fim.

## Vídeo de referência (estilo)

Se houver uma pasta de referência (`refs/` do projeto, ou a referência escolhida em `Referencias gerais/Videos de referencia/<Tipo>/` pela `produzir-video`), um `estilo.md`, ou o usuário pedir "edita no estilo de X", siga a skill `referencia-de-estilo` antes de editar para obter o `estilo.md` (reutilize se já existir). A partir daí:

- **O `estilo.md` manda** sobre os valores padrão desta skill: tamanho de pausa mantida, ritmo, regras de troca de enquadramento, abertura/encerramento, legendas e textos na tela. As regras de *o que cortar* (pato amarelo, retakes, falas fora do público) continuam valendo — elas são sobre limpeza, não estilo.
- Se o estilo pedir algo fora do material (ex.: zoom/punch-in sem ter câmera separada → use crop do próprio quadro; legenda → `render.py --build-subtitles` com estilo ajustado; animações → só se o usuário confirmar, via HyperFrames), faça o que for possível com ffmpeg e registre o restante em `edit/analise.md`.
- Ao final, rode a comparação de métricas descrita na skill de referência e faça **no máximo uma** rodada de ajuste se as métricas de ritmo estiverem >25% fora. Inclua a tabela resumida (referência × editado) no relatório.

Sem referência, use os padrões abaixo.

## O que cortar

1. **"Pato amarelo"** (e variações que o Whisper pode transcrever: "pato amarelo", "patamarelo", "pato, amarelo"). Significa: errei, vou repetir. Corte a palavra-chave **e** o trecho errado anterior — volte até o início da frase/ideia que foi repetida logo depois (compare o que vem antes e depois: o repetido é o que sobra). Normalmente é um erro curto (alguns segundos), mas se a frase repetida for longa, volte até onde ela começou. Em caso de dúvida, prefira cortar a frase inteira errada a deixar um pedaço quebrado.
2. **Retakes sem palavra-chave**: frases recomeçadas, falsos começos ("então o... então o que a gente faz"), mesma ideia dita duas vezes seguidas. Fique com a **última** versão completa, que costuma ser a boa.
3. **Silêncios e esperas**: pausas ≥ ~0,6s viram corte, deixando um respiro natural (~150–250ms) para não ficar picotado. Esperas longas (ex.: aguardando o Claude/um site carregar) somem por completo — mas se a tela mudar algo relevante nesse tempo, mantenha um trecho curto ou acelere em vez de cortar tudo.
4. **Muletas excessivas** (é..., hum..., tipo...) só quando estiverem isoladas entre pausas. Não mutile frases para tirar toda muleta; o vídeo deve continuar soando humano.
5. **Falas que obviamente não são para o público** (falar com alguém fora da câmera, "peraí, deixa eu ver", testes de áudio no começo/fim).

Cuidado com menções metalinguísticas: se o usuário estiver **explicando** a palavra-chave (ex.: "toda vez que eu erro eu falo pato amarelo"), isso é conteúdo, não marcador de corte. O contexto da frase deixa claro.

## Layout (cara cheia × cara+tela)

Detecte o formato pela inventário (`ffprobe` + um `timeline_view` de cada arquivo) e siga o caso:

- **2 arquivos sincronizados (cara cheia + cara-com-tela)**: mesmo áudio, mesma duração (confirme com `ffprobe`; se a duração diferir, alinhe pelo áudio antes de editar). Transcreva só um deles. Regra:
  - **Cara cheia** quando estiver apresentando/abrindo um assunto, na introdução, nas transições entre tópicos, opiniões e no encerramento.
  - **Cara+tela** quando estiver demonstrando algo, lendo, navegando, mostrando código/site/notícia — ou seja, quando a fala referencia o que está na tela ("olha aqui", "esse site", "clica aqui").
  - Em vídeo de compilado de notícias: cada notícia abre com cara cheia (~5–15s, até terminar a frase de apresentação) e depois passa para cara+tela até a próxima notícia.
  - Troque de layout só em fronteira de frase, nunca no meio. Evite trocas com menos de ~4s de duração.
  - No EDL, cada range aponta para o `source` correspondente (mesmos timestamps, arquivos diferentes).
- **Câmera e tela crus separados** (webcam + OBS): monte o layout cara+tela com ffmpeg (tela grande + câmera em quadro arredondado/canto, ou lado a lado) e use a câmera em tela cheia como "cara cheia". Mostre um frame de exemplo do layout ao usuário antes de renderizar tudo, pois é a única decisão estética relevante.
- **1 arquivo só**: sem troca de layout; apenas cortes.

## Fluxo

1. Ler `edit/project.md` se existir (retomar sessão).
2. Inventário: `ffprobe` de tudo, identificar o formato acima. Procurar referência/`estilo.md` (seção acima); se houver referência sem estilo, iniciar a análise em segundo plano junto com a transcrição.
3. Transcrever com `video-toolkit/scripts/transcribe.py` (fallback local automático), depois `pack_transcripts.py --edit-dir <edit>`.
4. Pré-varredura do `takes_packed.md`: listar todas as ocorrências de "pato amarelo", retakes, silêncios longos e a divisão em tópicos/notícias. Grave essa lista em `edit/analise.md` — ela é a base das decisões e ajuda o usuário a auditar depois.
5. Montar `edit/edl.json` com cortes + layout por range (`reason` curto em cada range: o que foi cortado antes dele e por quê).
6. `render.py edl.json -o edit/preview.mp4 --preview`, rodar a autoavaliação da video-use (cortes, pops de áudio, duração) e corrigir (máx. 3 passes).
7. Render final `edit/final.mp4` na resolução da fonte (normalmente 1080p) e entregar em `final/` (seção "Pastas").
8. Atualizar `edit/project.md` e responder com: arquivo entregue, duração bruta → final, nº de cortes por tipo (pato amarelo / retake / silêncio), divisão por tópico com timestamps no vídeo final (já serve de capítulos para o YouTube) e qualquer trecho em que ficou em dúvida.

## Fora do escopo (a menos que peçam)

Legendas, animações, color grade, música — a menos que o `estilo.md` da referência, o tipo de vídeo ou o briefing da `produzir-video` peça (aí use os assets das Referências gerais). Se pedirem animações/legendas elaboradas, sugira HyperFrames (via video-use) depois do corte pronto. Para cortes verticais de TikTok/Reels a partir do `final.mp4`, use a skill `cortes-verticais` depois (ela reaproveita o `edl.json` e as transcrições desta etapa).
