---
name: produzir-video
description: Porta de entrada para produzir vídeos a partir de uma pasta raiz de projetos. Pergunta a raiz, lê as Referências gerais (elementos gráficos, vídeos de referência, assets como logos/imagens/prints, sons, motions), abre o projeto pedido (material bruto em raw/, assets do projeto em assets/), aplica o tipo de vídeo (Vlog, Reels/Shorts, VSL, YouTube…) e as direções do usuário, gera tudo em edit/ e entrega em final/ com data, hora e título no nome. Use sempre que o usuário pedir "gera um vlog/reels/VSL da pasta X", "edita o projeto X", "produz um vídeo com o material de X" ou citar a pasta de projetos de vídeo — mesmo sem citar esta skill.
---

# Produzir vídeo (orquestrador)

Esta skill organiza **onde** as coisas ficam e **qual** skill faz cada parte. O corte em si continua nas skills `editar-video-youtube`, `cortes-verticais` e `referencia-de-estilo` (todas usam o `video-toolkit` e a `video-use`). Leia a skill de execução indicada pelo tipo antes de editar.

**Windows:** `PYTHONUTF8=1`. Script de apoio: `python ~/.claude/skills/produzir-video/scripts/projeto.py <comando>` (saída em JSON).

## Estrutura de pastas

```
<raiz>/                                   ← ex.: C:\Users\igorl\Videos\Videos Claude
├── Referencias gerais/                   ← qualquer nome com "referenc"; vale para todos os projetos
│   ├── Elementos graficos gerais/        ← placas, legendas, lower thirds (o NOME do arquivo diz quando usar)
│   ├── Videos de referencia/<Tipo>/<Nome>/   ← ex.: Vlog/Vlog Primo Rico visitando empresas/
│   │                                       estilo.md + _analise/ são gerados aqui e reaproveitados
│   ├── Assets/                           ← logos, imagens, prints, fotos usados em vários vídeos (ex.: logo do canal)
│   ├── Sons/                             ← trilhas, vinhetas, sfx
│   └── Motions/                          ← transições, animações, overlays com alfa
└── <Projeto>/                            ← ex.: Visita Beleza Completa Betim 03-11
    ├── raw/                              ← material bruto (NUNCA alterar, mover ou renomear)
    ├── assets/                           ← imagens, prints, logos, PDFs só deste projeto (ex.: logo da empresa visitada)
    ├── refs/                             ← opcional: referências só deste projeto (logo, cores, vídeo de exemplo)
    ├── edit/                             ← TUDO o que for gerado durante a produção
    │   ├── project.md                    ← memória do projeto (ler ao retomar; atualizar ao terminar)
    │   ├── briefing.md                   ← pedido + direções do usuário + assets escolhidos
    │   ├── transcripts/  takes_packed.md  edl.json  analise.md  verify/ …
    │   ├── <tipo>-<slug>/                ← quando houver mais de uma peça no projeto (ex.: reels-guardrails/)
    │   └── shorts/                       ← cortes verticais
    └── final/                            ← só entregáveis: "AAAA-MM-DD_HHMM - Título do vídeo.mp4"
```

Apelidos aceitos (projetos antigos): `material_bruto`/`brutos` = `raw`; `referencia`/`referencias` = `refs`; `imagens`/`arquivos` = `assets`. Mídia solta na pasta do projeto também conta como bruto — nesse caso pergunte se pode mover para `raw/` (é só renomear, não copia).

## Fluxo

1. **Raiz.** Rode `projeto.py raiz`. Se o usuário já citou a pasta raiz (ou o caminho completo do projeto) no pedido, use-a sem perguntar. Senão, pergunte numa mensagem curta sugerindo a última usada (`"raiz"` do JSON), por ex.: *"Uso a pasta de projetos `C:\…\Videos Claude`, ou é outra?"*. Depois grave com `projeto.py raiz --set <pasta>`.

2. **Inventário.** `projeto.py scan <raiz>` lista as referências gerais por categoria e os projetos. Identifique o projeto pelo nome citado (aceite aproximações: "a da Beleza Completa"). Se houver ambiguidade, pergunte junto com o passo 4.

3. **Preparar o projeto.** `projeto.py init <pasta_do_projeto>` cria `assets/`, `edit/` e `final/` e devolve onde estão `raw/`, `assets/` (com a lista de arquivos), `refs/`, `estilo.md` e `project.md`. Se existir `edit/project.md`, leia e retome dali.

4. **Briefing.** Junte o pedido em `edit/briefing.md`: tipo, título provisório, duração alvo, público/plataforma, empresa/marca (cores), direções do usuário ("abre com o fulano", "sem música", "destaque o número X"), referência escolhida e assets escolhidos. Pergunte **uma única vez, tudo junto**, só o que for ambíguo e mudar o resultado (ex.: tipo não informado, cores da empresa sem logo em `refs/`). O resto, decida e registre no briefing.

5. **Referência de estilo.** Ordem de prioridade: `refs/` do projeto → `Videos de referencia/<Tipo>/` que bate com o tipo pedido → estilos salvos em `~/.claude/skills/referencia-de-estilo/estilos/` → padrões da skill de execução. Se a referência ainda não tem `estilo.md`, rode a `referencia-de-estilo` **apontando para a pasta da referência** (o `estilo.md` e `_analise/` ficam lá e servem para os próximos projetos), em segundo plano junto com a transcrição.

6. **Assets.** Antes de montar, olhe os elementos, sons e motions das Referências gerais (abra os PNGs; para vídeo/motion extraia 1 frame). **O nome do arquivo é a instrução de uso** (ex.: "Placa de título — use para lugares, pessoas, títulos, data — utilize as cores da empresa…"): siga-o. Reproduza o visual (posição, proporção, fonte, cor, caixa) em overlays gerados (PIL/ffmpeg ou HyperFrames), trocando texto e cores conforme o briefing; use o arquivo direto quando ele for o próprio asset (som, motion com alfa, logo). Registre no briefing qual asset foi usado onde.
   - **Assets (imagens, prints, logos, fotos, PDFs):** prioridade `<Projeto>/assets/` → `Referencias gerais/Assets/`. Abra cada imagem para saber o que é (o nome do arquivo também orienta: "logo-beleza-completa.png", "print-dashboard.png"). Use como inserts sobre a fala que cita aquilo (print quando falam do sistema, logo na placa de título/abertura, foto como b-roll), em tela cheia sobre fundo desfocado ou num canto, por 2–5 s, com leve zoom se ficar parado. Logo da empresa define as cores das placas. PDF/slide: renderize a página como imagem em `edit/`. Nunca altere o arquivo original — versões recortadas/redimensionadas vão para `edit/assets/`.
   - Sons: só entram se o tipo/estilo pedir trilha ou o usuário mandar; trilha a ~-20 dB sob a fala (ducking), vinhetas no volume da fala.
   - Pastas vazias são normais — siga sem o asset e avise no relatório.

7. **Executar** com a skill do tipo (tabela abaixo), sempre com `--edit-dir <projeto>/edit` e lendo os brutos de `raw/`. Todos os arquivos intermediários (scripts, overlays, previews, renders) ficam em `edit/`. Nada é escrito em `raw/`, nas Referências gerais (exceto `estilo.md`/`_analise/` da referência) ou dentro das skills.

8. **Entregar.** Para cada vídeo pronto:
   `projeto.py entregar <edit/.../final.mp4> --projeto <pasta_do_projeto> --titulo "<Título do vídeo>"`
   Move para `final/AAAA-MM-DD_HHMM - Título.mp4` (data/hora do momento da entrega; caracteres inválidos saem; nomes repetidos ganham `(2)`). Use `--copiar` se a skill de execução ainda precisar do arquivo em `edit/` (ex.: `cortes-verticais` depois do vídeo longo). Thumbnails e textos de post entregues vão com o mesmo prefixo (`… - Título - thumb.png`, `… - Título - post.md`).

9. **Fechar.** Atualize `edit/project.md` (estado, decisões, assets usados, arquivos em `final/`) e responda com: arquivos entregues, duração, referência e assets usados, e dúvidas.

## Tipos de vídeo

| Tipo pedido | Executor | Formato | Notas |
|---|---|---|---|
| Vlog, visita, evento, YouTube longo, aula | `editar-video-youtube` | 16:9, resolução da fonte | Estilo da referência `Vlog/` quando houver. Placas de título para lugares/pessoas. |
| Reels / Shorts / TikTok a partir de um longo já editado | `cortes-verticais` | 9:16, 45 s–3 min | Entrada: o final do longo (entregue com `--copiar`) ou `edit/final.mp4`. Saída em `edit/shorts/`, cada corte entregue em `final/`. |
| Reels / Shorts direto do bruto | `editar-video-youtube` (limpeza) → `cortes-verticais` | 9:16, 15–90 s | Primeiro um corte enxuto em `edit/reels-<slug>/`, depois o vertical. Legenda queimada (o asset de legenda manda no visual). Gancho nos 2 primeiros segundos. |
| VSL (vídeo de vendas) | `editar-video-youtube` | 16:9 ou 9:16 conforme briefing | Estrutura gancho → problema → solução → prova → oferta → CTA. Cortes secos, sem respiros longos, legenda queimada, placas de informação para números/provas. Confirme a oferta/CTA no briefing se não estiver na fala. |
| Outro tipo | o mais próximo acima | — | Procure `Videos de referencia/<Tipo>/`; registre no briefing as regras adotadas. |

Se o usuário pedir mais de uma peça do mesmo projeto, cada uma ganha sua subpasta em `edit/` e seu arquivo em `final/`; transcrições em `edit/transcripts/` são compartilhadas (cache, nunca retranscrever).

## Regras

- `raw/` e `assets/` são somente leitura. Caminhos no `edl.json` relativos a `edit/` (ex.: `"../raw/DJI_0246.MP4"`).
- `final/` só recebe entregáveis aprovados pelo fluxo (render final, não preview).
- `timeline_view.py` procura a transcrição em `<pasta do vídeo>/edit/`; como os brutos ficam em `raw/`, passe `--transcript <projeto>/edit/transcripts/<nome>.json` e `-o <projeto>/edit/verify/<arquivo>.png`.
- Não espere confirmação a cada passo: depois do briefing, vá até o fim (preferência do usuário).
