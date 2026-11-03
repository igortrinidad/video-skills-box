---
name: referencia-de-estilo
description: Analisa um ou mais vídeos de referência (do próprio canal ou de outro criador) e extrai o estilo de edição — ritmo de cortes, pausas mantidas, enquadramentos, abertura/encerramento, legendas, textos na tela, volume — num estilo.md que guia a edição dos vídeos brutos e dos cortes verticais. Também compara o vídeo editado com a referência. Use sempre que o usuário mandar uma pasta "referencia", disser "edita igual a esse vídeo", "nesse estilo", "copia o ritmo do fulano", ou quando houver uma pasta de referência ao lado dos brutos.
---

# Referência de estilo → estilo.md

Objetivo: transformar "quero que fique parecido com esse vídeo" em regras concretas e mensuráveis que as skills `editar-video-youtube` e `cortes-verticais` conseguem seguir, e depois conferir com números se o resultado chegou perto.

Você não assiste ao vídeo como uma pessoa. Você entende a referência por **métricas** (cortes, ritmo de fala, pausas, volume), **frames** (contact sheet) e **transcrição**. Seja honesto no estilo.md sobre o que dá para imitar e o que não dá.

**Windows:** `PYTHONUTF8=1`; escreva JSON/MD com o tool de escrita de arquivos.

## Organização de pastas esperada

```
meu-projeto/
├── referencia/          ← vídeo(s) de referência (horizontal e/ou vertical)
│   ├── _analise/        ← gerado: métricas, frames, transcrições
│   └── estilo.md        ← gerado: o estilo destilado
└── brutos/              ← gravações a editar (saída em brutos/edit/)
```

Aceite variações (nomes diferentes, referência solta). Se houver referências horizontais e verticais, gere um estilo para cada formato (seções separadas no mesmo estilo.md).

## Fluxo

1. **Já existe `estilo.md`?** Se existir e as referências não mudaram, reutilize — não reanalise. Também verifique `~/.claude/skills/referencia-de-estilo/estilos/` se o usuário citar um estilo pelo nome ("usa o estilo do episódio 22").

2. **Medir.** A transcrição usa o `video-toolkit` (Groq, rápido; cai para Whisper local se falhar, e aí demora — nesse caso rode em segundo plano). A detecção de cortes e o contact sheet levam alguns minutos em vídeos longos:
   ```
   python ~/.claude/skills/referencia-de-estilo/scripts/analyze_video.py <pasta_referencia>
   ```
   - Talking head com jump cuts (mesmo fundo, mesma pessoa) mal muda a imagem: se `shots` vier muito baixo para o que o vídeo aparenta, rode de novo com `--scene 0.12`. Em vídeo com muita tela/movimento, 0.25–0.35 evita falsos cortes.
   - Referência muito longa (> 30 min): tudo bem, mas use `--max-frames 60`.

3. **Olhar.** Leia `_analise/<video>/contact_sheet.png` (cada frame tem nº do plano, tempo e duração). Para entender abertura e encerramento, extraia frames extras dos primeiros 15s e dos últimos 15s (`ffmpeg -ss T -i v -frames:v 1 ...`). Identifique:
   - tipos de enquadramento usados (cara cheia, cara+tela lado a lado, tela cheia, tela com câmera no canto, zoom/punch-in, b-roll) e a proporção aproximada de cada um;
   - em que momentos troca (início de assunto, demonstração, ênfase);
   - legenda: existe? posição, tamanho relativo, caixa alta, cor, palavras por vez, destaque de palavra;
   - texto na tela, títulos de seção, gancho visual no início, vinheta, encerramento/CTA.

4. **Ler a transcrição** (`_analise/<video>/transcripts/*.json`; rode `pack_transcripts.py --edit-dir _analise/<video>` para ver por frases). Observe: como abre (gancho direto ou apresentação), como transita entre assuntos, se mantém muletas, como encerra.

5. **Escrever `estilo.md`** na pasta de referência, no formato abaixo. Salve uma cópia em `~/.claude/skills/referencia-de-estilo/estilos/<nome-curto>.md` para reuso em outros projetos.

6. **Depois da edição, comparar** (as skills de edição chamam isto no final):
   ```
   python ~/.claude/skills/referencia-de-estilo/scripts/analyze_video.py <final.mp4> --out <edit>/_analise
   python ~/.claude/skills/referencia-de-estilo/scripts/analyze_video.py --compare <ref>/_analise/<v>/metrics.json <edit>/_analise/final/metrics.json
   ```
   Use o mesmo `--scene` da referência. Diferenças que importam: `speech.pause_p90_s`, `speech.pauses_over_0_5s_per_min`, `speech.words_per_min` (ritmo), `shots_per_min` (só se a referência corta muito mais/menos), `loudness_lufs`. Uma diferença acima de ~25% nas métricas de ritmo vale uma rodada de ajuste; duração total depende do conteúdo e não precisa bater.

## Formato do estilo.md

```markdown
# Estilo: <nome> (<referências usadas>)

## Resumo em uma frase
<ex.: "Ritmo rápido, quase sem respiro, alterna cara cheia e tela a cada assunto, sem legenda.">

## Alvos numéricos (horizontal)
- Pausa máxima mantida entre frases: ~X s (p90 da referência: Y s)
- Pausas ≥0,5s por minuto: ~N
- Ritmo de fala resultante: ~W palavras/min
- Planos por minuto: ~S (duração mediana Z s)
- Volume: -14 LUFS

## Enquadramento
- Tipos usados e proporção: ...
- Regras de troca: ...
- Mudanças sem troca de câmera (zoom/punch-in a cada N s?): ...

## Abertura e encerramento
...

## Legendas e textos na tela
...

## Vertical (se houver referência vertical)
- Duração típica, gancho, layout (face/stack/fit), legenda (posição, palavras por vez), texto de topo...

## O que não dá para replicar automaticamente
<animações, efeitos, trilha específica... + sugestão (HyperFrames, etc.) se o usuário quiser>
```

Escreva alvos como faixas e explique o porquê quando não for óbvio — quem edita vai precisar decidir casos de borda.
