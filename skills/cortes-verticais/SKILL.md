---
name: cortes-verticais
description: Transforma um vídeo horizontal longo já editado (episódio do YouTube, compilado de notícias, aula, live) em vários cortes verticais 9:16 de 1–3 minutos, um por assunto/notícia, prontos para TikTok, Instagram Reels e YouTube Shorts, com legenda queimada. Use sempre que o usuário pedir cortes, shorts, reels, vídeos verticais, "picar o episódio", "fazer os cortes pro TikTok/Instagram" ou quiser divulgar trechos de um vídeo longo — inclusive logo depois de usar a skill editar-video-youtube.
---

# Cortes verticais (TikTok / Reels / Shorts)

Entrada: um vídeo horizontal editado (normalmente `<Projeto>/edit/final.mp4` gerado pela skill `editar-video-youtube`). Saída de trabalho: `<Projeto>/edit/shorts/NN-slug.mp4` em 1080×1920 + um `shorts/README.md` com título, legenda de post e hashtags de cada corte.

Entrega (projetos da skill `produzir-video`, com `raw/`/`edit/`/`final/`): cada corte aprovado vai para `final/` com `python ~/.claude/skills/produzir-video/scripts/projeto.py entregar <edit/shorts/NN-slug.mp4> --projeto <Projeto> --titulo "Reels - <título do corte>" --info edit/shorts/NN-slug-info.txt --copiar`; o info.txt de cada corte segue o formato da seção "info.txt" da `produzir-video` (título, legenda curta, hashtags; sem capítulos). Visual da legenda: siga o asset de legenda das Referências gerais quando existir.

Rode tudo sem pedir confirmação a cada passo; o usuário quer receber os cortes prontos. Pergunte só se não houver como decidir sozinho (ex.: não dá pra achar a câmera no frame).

**Windows:** use `PYTHONUTF8=1` e escreva JSON com o tool de escrita de arquivos (sem BOM).

## Ferramentas

Scripts nesta skill (`~/.claude/skills/cortes-verticais/scripts/`):

- `remap_transcript.py <edit_dir>` — se o `final.mp4` veio da skill de edição, converte as transcrições brutas para a linha do tempo do final usando `edl.json`. Sai em `edit/transcripts_final/final.json`. **Prefira isso a retranscrever** (mantém a linha do tempo idêntica à da edição).
- Se não houver `edl.json` (vídeo editado em outro lugar), transcreva o próprio vídeo: `python ~/.claude/skills/video-toolkit/scripts/transcribe.py <video> --edit-dir <dir> --language pt` (rápido, via Groq; cai para Whisper local se falhar; se parar com `MISSING_API_KEY`, veja "Sem chave do Groq" no SKILL.md do `video-toolkit`) e depois `pack_transcripts.py` da video-use para ler.
- `make_short.py <spec.json> [--preview]` — renderiza um corte a partir de um spec JSON (formato documentado no topo do script): trechos, layout por trecho, caixas de recorte, legenda e gancho opcional no topo nos primeiros 3s. Cuida de fades de 30ms, concat, legenda e loudness -14 LUFS.
- `~/.claude/skills/video-use/helpers/timeline_view.py` e `ffmpeg -ss T -frames:v 1` para ver frames.

## Referência de estilo

Se houver referência vertical (short/reel de exemplo) ou um `estilo.md` com seção "Vertical", siga a skill `referencia-de-estilo` para obtê-lo e use os valores dele no lugar dos padrões abaixo: duração dos cortes, tipo de gancho, layouts (`face`/`stack`/`fit`) e proporção, posição/estilo da legenda (`caption_margin`; para mudar fonte/tamanho/cor ajuste o `style` em `make_short.py` via cópia local, não edite o original) e texto no topo. Uma referência só horizontal não define o vertical — nesse caso use os padrões. Depois de renderizar, compare um corte com a referência vertical pelo `--compare` e ajuste se o ritmo estiver >25% fora.

## Fluxo

1. **Transcrição na linha do tempo do vídeo de entrada** (remap ou transcrever). Para ler com conforto, gere a versão por frases: copie o JSON para uma pasta `transcripts/` temporária e rode `pack_transcripts.py`, ou leia o JSON direto se for curto.
2. **Escolher os cortes.** Um corte por notícia/assunto autocontido. Para cada um:
   - Começa num gancho forte — a frase que faz a pessoa parar de rolar (a novidade, o número, a opinião). Se a apresentação da notícia for morna, comece pela frase mais forte e, se precisar, volte para o contexto em seguida (pode reordenar trechos).
   - Termina numa conclusão/opinião, não no meio de raciocínio. Corte vinhetas, "no próximo assunto", chamadas para o canal e referências ao vídeo longo ("como eu falei antes", "lá no começo do episódio") que não fazem sentido isoladas.
   - Duração alvo 45s–3min; abaixo de ~30s só se for muito forte.
   - Pode juntar trechos não contíguos do mesmo assunto; sempre em fronteira de palavra, com respiro de ~80–120ms.
   - Pule assuntos fracos ou que dependem demais do resto do vídeo — melhor 5 bons cortes que 9 medianos. Normalmente sai próximo de 1 corte por notícia.
3. **Achar as caixas de recorte (uma vez por vídeo).** Extraia 1 frame de cada layout presente (cara cheia e cara+tela) e olhe:
   - `face`: retângulo em volta da pessoa (inclua ombros, deixe ar acima da cabeça). Na cara cheia o rosto geralmente está centralizado; na cara+tela está no quadro lateral.
   - `screen`: área útil da tela do computador, sem a câmera.
   Escreva as coordenadas em pixels do vídeo fonte. Se a câmera mudar de posição entre layouts, use specs/segmentos com caixas diferentes (um spec por corte; separe em dois trechos se precisar).
4. **Layout por trecho dentro do corte:**
   - Trecho em que o vídeo fonte mostra cara cheia → `face`.
   - Trecho com tela relevante → `stack` (tela em cima, rosto embaixo). Se a tela for ilegível mesmo assim (texto muito pequeno), prefira `face` ou `fit`.
   - Material sem rosto (só tela, b-roll) → `fit`.
   Os trechos devem acompanhar as trocas de layout do vídeo fonte — confira o frame no início de cada trecho.
5. **Spec e render.** Um `edit/shorts/specs/NN-slug.json` por corte, `output` em `../NN-slug.mp4`. Rode primeiro um corte com `--preview`, extraia 3 frames (início, meio, fim) e confira enquadramento e legenda (a legenda fica a ~30% da base para fugir da interface do TikTok/Reels; ajuste `caption_margin` se cobrir algo importante). Depois rode todos em modo final.
   - `hook`: frase curta (até ~7 palavras) só quando o começo precisar de contexto visual; não repita o que a pessoa fala.
   - Legendas sempre ligadas, a não ser que o usuário diga o contrário. Corrija nomes próprios/termos técnicos que o Whisper errar editando o JSON de transcrição antes do render (não o vídeo).
6. **Verificar.** `ffprobe` de cada saída (1080×1920, duração esperada) e um frame de cada. Se algo estiver errado, corrija e renderize de novo (máx. 3 vezes por corte).
7. **Entregar.** `edit/shorts/README.md` com, para cada corte: arquivo, duração, de onde saiu (timestamps no vídeo fonte), título curto, legenda pronta para post (1–3 frases + CTA leve) e 3–6 hashtags relevantes. Responda ao usuário com a lista resumida.

## Publicação

Esta skill não publica. Se o usuário pedir para subir como rascunho no TikTok/Instagram, use a integração que ele tiver configurada (MCP/skill de publicação); se não houver, entregue os arquivos e o README para upload manual.
