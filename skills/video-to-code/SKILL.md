---
name: video-to-code
description: Recebe um link de vídeo do YouTube (tutorial, aula, live coding, palestra técnica), baixa o vídeo, disseca o que é mostrado na tela com screenshots e transcreve todo o código relevante ao tema para arquivos reais, montando um projeto executável com README passo a passo, transcrição da fala e prints de conferência, numa pasta escolhida pelo usuário. Use sempre que o usuário mandar um link do YouTube e pedir o código do vídeo, "transcreve o código desse tutorial", "tira o código desse vídeo", "quero o projeto desse vídeo", "documenta esse tutorial com prints", ou quiser estudar/reproduzir o que foi programado num vídeo — mesmo sem citar esta skill.
---

# Vídeo do YouTube → código + guia

Objetivo: o usuário termina com uma pasta onde consegue **ler o tutorial sem assistir** (README com prints e timestamps), **rodar o código** (projeto em `codigo/`) e **conferir cada arquivo** contra a tela original (prints em `conferencia/`).

Você não assiste ao vídeo: você o entende por **frames** (lidos com a sua visão) e pela **transcrição** da fala. O código precisa sair da tela, não da sua memória — quando algo não estiver legível, marque como incerto em vez de inventar. Um código "parecido" que não é o do vídeo quebra a confiança do usuário no resto da entrega.

**Windows:** `PYTHONUTF8=1` (PowerShell: `$env:PYTHONUTF8="1"`). Escreva arquivos de código e Markdown com a ferramenta de escrita de arquivos, não com `echo`.

Script (todas as etapas): `python ~/.claude/skills/video-to-code/scripts/video_to_code.py <comando> ...` — abaixo abreviado como `vtc`.

## Estrutura entregue

```
<destino>/<Título do vídeo>/
├── README.md          ← guia passo a passo com prints, timestamps e links para o código
├── CONFERENCIA.md     ← cada arquivo de código → prints de onde foi transcrito + incertezas
├── transcricao.md     ← fala com marcas [hh:mm:ss]
├── codigo/            ← projeto executável (estrutura de pastas como no vídeo)
├── screenshots/       ← prints escolhidos para ilustrar o README
├── conferencia/       ← prints das telas de código, um subdiretório por arquivo
├── video/             ← o .mp4 baixado, .info.json e legendas
└── _trabalho/         ← frames brutos, contact sheets, cache de transcrição (pode apagar)
```

## Fluxo

### 1. Perguntar onde salvar

Rode `vtc destino` para ver o último destino usado. Pergunte ao usuário (uma mensagem só, com a ferramenta de perguntas se houver) em qual pasta salvar, oferecendo o último destino como primeira opção quando existir. Grave a resposta com `vtc destino --set <pasta>`. Não comece o download antes da resposta — o vídeo vai direto para lá.

Se o usuário mandar vários links, pergunte o destino uma vez e processe cada vídeo na sua própria subpasta.

### 2. Baixar

```
vtc baixar <url> --destino <pasta>
```

Baixa em até 1080p (código fica legível; use `--max-height 1440` se a fonte do editor for muito pequena), junto com metadados e legendas do YouTube. A saída JSON traz `pasta`, título, canal, duração, **capítulos** e **descrição** — leia os dois: capítulos dão a estrutura do README e a descrição costuma ter link do repositório, versões das libs e comandos.

- Se a descrição tiver link para um repositório oficial (GitHub etc.), avise o usuário e use-o só como **conferência** de trechos ilegíveis, deixando claro no CONFERENCIA.md quais trechos vieram de lá. A transcrição continua sendo do vídeo — é o que o usuário pediu.
- Vídeo privado, com restrição de idade ou de membros: o yt-dlp falha; peça ao usuário um arquivo local ou cookies (`--cookies-from-browser`) em vez de tentar contornar.
- Arquivo local em vez de link: crie `<destino>/<nome>/video/` e copie o arquivo para lá; o resto do fluxo é igual.

### 3. Transcrever a fala (em paralelo com os frames)

```
vtc transcrever <pasta> --language pt      # ou en; omita para detectar
```

Usa o `video-toolkit` (Groq, rápido). Se parar com `MISSING_API_KEY`, siga "Sem chave do Groq" no SKILL.md do `video-toolkit` — mas ofereça também `--legenda`, que usa a legenda do YouTube (instantânea, sem chave, menos precisa). Gera `transcricao.md`. Rode em segundo plano enquanto extrai os frames.

### 4. Extrair frames

```
vtc frames <pasta>
```

Amostra o vídeo a cada 2s, agrupa em **telas** (trechos sem mudança grande de imagem) e guarda em resolução cheia: o primeiro frame de cada tela, frames onde o conteúdo cresceu (digitação, scroll) e o **último frame de cada tela** — normalmente o que tem o código mais completo. Gera contact sheets numerados (`_trabalho/contact/contact_NN.png`, 20 frames cada, com `#n`, tempo e nº da tela) e o índice `_trabalho/frames.json`.

Ajustes:
- Live coding com digitação lenta → muitos frames quase iguais: `--step 0.06`.
- Slides/tela que mudam pouco e frames demais faltando → `--screen 0.25 --step 0.02`.
- Vídeo > 1h: `--every 3`.

### 5. Mapear o vídeo

Leia os contact sheets em ordem, junto com `transcricao.md` e os capítulos. Monte para você um mapa com:
- **seções** do tutorial (início/fim, o que se faz em cada uma);
- quais telas mostram **código relevante ao tema** e de qual arquivo (nome na aba/árvore do editor, título do terminal);
- comandos de terminal (instalação, execução), arquivos de configuração, saídas esperadas;
- o que é ruído: rosto do apresentador, propaganda/patrocínio, intro/outro, código de outro assunto mostrado de passagem.

"Relevante ao tema" = o que o espectador precisaria digitar para reproduzir o resultado do vídeo. Patrocínio e trechos fora do tema ficam de fora do código (cite no README se ajudar a entender pulos de tempo).

### 6. Transcrever o código

Para cada arquivo de código, abra os frames de resolução cheia em `_trabalho/frames/` (o contact sheet é pequeno demais para ler código):

1. Pegue o frame **mais tardio** em que o arquivo aparece por completo naquela versão; leia linha a linha.
2. Se o arquivo rola para fora da tela, combine os frames de scroll pela sobreposição de linhas — não duplique nem pule linhas.
3. Texto pequeno ou borrado: recorte e amplie a região com `vtc crop <frame> --box x,y,w,h --scale 2` e leia o recorte. Se faltar um momento, extraia com `vtc frame <pasta> --at 12:34`.
4. Cruze com a fala: o apresentador costuma soletrar nomes, portas, versões e explicar o que digitou.
5. Se o arquivo **evolui** ao longo do vídeo, a versão em `codigo/` é a **final** do vídeo. Mudanças intermediárias importantes ficam como trechos no README, na seção onde acontecem.
6. Respeite exatamente nomes, indentação e estilo do vídeo. Não "melhore" o código. Correções só quando o código do vídeo não roda (erro de digitação que o próprio apresentador corrige depois, por exemplo), e sempre registradas no CONFERENCIA.md.
7. Trecho ilegível: escreva sua melhor leitura com um comentário `# TODO(video-to-code): ilegível em 12:34 — conferir` (na sintaxe de comentário da linguagem) e liste no CONFERENCIA.md.

Salve os prints de conferência de cada arquivo com `vtc frame <pasta> --at <t1> --at <t2> --into conferencia/<caminho-do-arquivo-com-hifens>` (ex.: `conferencia/src-routes-users.ts/`), incluindo todos os frames de scroll usados.

### 7. Montar o projeto executável

Em `codigo/`, reproduza a estrutura de pastas do vídeo (árvore do editor). Inclua o que o vídeo usa para rodar, mesmo que só apareça no terminal ou na fala: `package.json`/`requirements.txt`/`pyproject.toml`/`go.mod`, `.env.example` (nunca segredos reais vistos na tela — substitua por placeholders e avise), `Dockerfile`, etc. Versões de dependência: use as mostradas no vídeo/descrição; se não aparecerem, deixe sem fixar e diga isso no README.

Se o ambiente permitir, faça uma verificação barata (instalar dependências e compilar/`python -m py_compile`/`tsc --noEmit`/`node --check`) e registre o resultado. Não rode nada que precise de credenciais, serviços pagos ou que altere o sistema do usuário.

Se o vídeo não mostra código suficiente para um projeto rodar (palestra conceitual, só trechos soltos), não invente o resto: entregue os trechos como arquivos separados em `codigo/trechos/` e explique no README.

### 8. Screenshots do README

Escolha prints que ajudam a entender sem assistir: resultado final rodando, diagramas/slides explicativos, configurações em telas de interface (dashboards, consoles de nuvem), saída do terminal. Copie-os para `screenshots/` com nome descritivo (`03-tela-de-login-funcionando.png`). Evite prints só de código no README — o código já está nos arquivos; prints de código vão para `conferencia/`.

### 9. Escrever README.md e CONFERENCIA.md

Use os formatos abaixo. Links relativos, para funcionar no GitHub, VS Code e Obsidian. Timestamps como links para o vídeo no momento exato: `[12:34](https://youtu.be/<id>?t=754)`.

### 10. Conferir e entregar

Antes de dizer que terminou:
- todo arquivo citado no README existe em `codigo/` e todo arquivo em `codigo/` tem entrada no CONFERENCIA.md;
- todo print referenciado existe;
- releia cada arquivo de código ao lado do seu último print de conferência, procurando linhas faltando, parênteses/chaves desbalanceados, nomes trocados.

Responda ao usuário com: caminho da pasta, quantos arquivos de código, quantos trechos incertos (e onde), resultado da verificação de execução e como rodar.

## Formato do README.md

~~~markdown
# <Título do vídeo>

> Canal: <canal> · Publicado: <data> · Duração: <hh:mm:ss> · [Assistir](<url>)

## Resumo
<2–4 frases: o que é construído, com quais tecnologias, e o resultado final.>

![Resultado final](screenshots/NN-resultado.png)

## Pré-requisitos
- <ferramentas e versões mostradas/citadas>

## Como rodar
```bash
cd codigo
<comandos do vídeo>
```

## Estrutura do projeto
```
<árvore de codigo/>
```

## Passo a passo
### 1. <Seção> — [mm:ss](<url>?t=N)
<o que é feito e por quê, em prosa curta, baseado na fala>
- Arquivo: [`src/app.py`](codigo/src/app.py)
<trechos intermediários relevantes, se o arquivo mudou depois>
![<descrição>](screenshots/NN-....png)

### 2. ...

## Observações
<diferenças entre o vídeo e o código entregue, versões não fixadas, partes fora do tema omitidas, links da descrição>
~~~

## Formato do CONFERENCIA.md

```markdown
# Conferência do código

| Arquivo | Transcrito de | Prints |
|---|---|---|
| `src/app.py` | [12:34](<url>?t=754)–[15:10](<url>?t=910) (versão final) | [3 prints](conferencia/src-app.py/) |

## Incertezas
- `src/app.py` linha 42: valor da porta ilegível em 12:50; lido como `8000` pela fala.

## Correções feitas em relação ao vídeo
- `src/db.py`: o vídeo mostra `improt` em 08:12 e corrige em 09:30; entregue já corrigido.

## Fontes externas
- <trechos conferidos no repositório da descrição, se houver>
```
