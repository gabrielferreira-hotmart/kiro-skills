---
name: harness-metrics-use
description: "Analisa localmente o histórico de sessões do Kiro (IDE + CLI) e gera um relatório HTML com métricas de qualidade e eficiência do uso do harness, geral e por repositório. Local-first e somente-leitura. Use ao pedir para analisar/medir o uso do Kiro, gerar relatório de qualidade das sessões, ou comparar dois períodos (baseline vs after)."
keywords:
  - harness-metrics
  - kiro-usage
  - quality
  - efficiency
  - sessions
  - local-first
  - report
  - hotmart
metadata:
  author: Samuel Silva
  version: "1.0.0"
---

# Harness Metrics Use

Transforma o histórico de sessões do Kiro em um diagnóstico objetivo de **qualidade** e
**eficiência** do uso do harness, com suporte a experimentos **baseline → after**.

A skill separa rigorosamente dois graus de confiança e **essa distinção é o contrato
central** — nunca a apague ao apresentar resultados:

- 🟢 **Determinística** — calculada a partir de eventos concretos do log (timestamps,
  exit codes, `success`, `filePath`, `contextUsage`). Reprodutível, sem interpretação.
  É um **fato**.
- 🟡 **Tendência** — envolve interpretação semântica (classificar uma mensagem como
  correção, inferir alucinação por linguagem, julgar first-pass). Serve para **direção e
  comparação relativa**, não como valor absoluto. É um **indicador**.

## Princípios inegociáveis

1. **Somente leitura sobre o histórico.** Nunca modificar, mover ou apagar nada em
   `~/.kiro/`. Toda saída vai para um diretório de trabalho separado (ver Passo 5).
2. **Local-first.** O relatório padrão não contém código-fonte, prompts completos nem
   caminhos sensíveis. Só métricas, contagens, scores, IDs anonimizados e — quando
   estritamente necessário — trechos de evidência truncados.
3. **Determinístico primeiro.** Coleta e cálculo são sempre por script determinístico.
   Interpretação semântica é isolada, opcional e desligada por padrão.
4. **LLM externo é opt-in explícito.** Qualquer envio de conversa/código para um modelo
   externo (judge semântico) é exfiltração de dados proprietários — só com flag explícita
   e aviso ao usuário.
5. **A classe da métrica viaja com o dado.** Cada métrica carrega o campo `class`
   (`deterministic` | `trend`) desde a origem. A apresentação só reflete — nunca decide.

## Fonte de dados

O armazenamento e o schema dos eventos estão documentados em
[`references/event-schema.md`](references/event-schema.md). Em resumo:

```
~/.kiro/sessions/<workspace-hash>/<session-uuid>/
├── session.json        # metadados (id, title, agentMode, modelId, timestamps, status)
└── messages.jsonl      # event log: user, assistant, turn_start/end, tool_call,
                        # tool_result, steering_inclusion, session_metadata (contextUsage),
                        # pending_interaction, interaction_resolved
```

**Créditos e tempo por sessão:** quando o Kiro registra `usage_summary.promptTurnSummaries`
(créditos por turno) e `usage_summary.elapsedTime` (tempo real), a skill lê e reporta como
🟢. Nem toda versão popula esses campos; quando ausentes, as métricas de consumo
simplesmente não aparecem (sem afirmar que são "impossíveis"). Tokens brutos (input/output)
por sessão de IDE seguem indisponíveis. Ver `references/event-schema.md` §Consumo.

**Rollup de time:** para custo agregado por usuário/time, a fonte oficial é o **CSV diário
do Kiro Enterprise no S3** (`Date, UserId, Client_Type, Credits_Used, ...`). A skill local
é complementar: mede o que o CSV não tem — tool calls, retrabalho, alucinação, esforço de
descoberta. Não junte histórico local de várias pessoas para isso; use o CSV.

**Analisar sessão de outra pessoa:** o `Export Chat` do Kiro gera um zip com o mesmo layout
(`session.json` + `messages.jsonl` + `sub-executions/*.jsonl`). Dá para analisar sem tocar
no `~/.kiro/` de ninguém apontando a skill para o export descompactado.

## Fluxo

Modo **principal**: relatório de **período único** — analisa um recorte e gera o HTML,
sem comparar com nada. Modo **opcional**: comparar dois períodos (ver
[`references/baseline-after.md`](references/baseline-after.md)).

### Passo 1 — Definir o período

```
--from <ISO-date> --to <ISO-date> --label <ex: 2026-08>
```

O label é só um nome para o snapshot/arquivo. A data seleciona as sessões; o snapshot
congela as métricas.

### Passo 2 — Coletar e segmentar

Rode `scripts/collect.py` (seleciona sessões pelo período e workspace, incorpora
`sub-executions/*.jsonl`, normaliza eventos) seguido de `scripts/segment.py`.

**Período:** a sessão é **selecionada** pelo período (createdAt/lastModifiedAt cruzam a
janela) e então **todos os seus eventos** entram — não truncamos sessões que cruzam a
fronteira. `--to YYYY-MM-DD` inclui o **dia inteiro**. Datas só-dia são interpretadas em
UTC; passe ISO 8601 com offset para outro fuso.

**Validação de formato:** NÃO barramos por `schemaVersion` (ele ficou `1.0.0` antes e
depois de uma quebra real de vocabulário de `actionType`). Quem detecta a quebra é o
canário `unmappedActionTypes` no snapshot: se muitos `actionType` não forem reconhecidos,
o report avisa e os aliases em `scripts/actions.py` precisam ser atualizados.

**Escopo (workspace):** por padrão analisa **todos os repositórios** onde o Kiro foi
usado. O report sempre traz a visão **geral** (todos juntos) no topo e a quebra **por
repositório** mais abaixo. Use `--workspace <path>` só se quiser restringir a um projeto.

**Origem (surface):** por padrão coleta **IDE + CLI** (`--surface all`). O CLI é
normalizado por `collectors_cli.py` para o mesmo modelo do IDE. Sessões CLI de
**automação** (subagent/cron/hook) são ignoradas por padrão — use `--include-automation`
para incluí-las. Cada sessão carrega `surface` e o report mostra a distribuição.
Limitações do CLI (sem timestamp por evento, sem contextUsage) estão em
[`references/event-schema.md`](references/event-schema.md).

A segmentação usa um **score multi-sinal** (não regex sozinha): combina gap temporal,
troca dos arquivos tocados, `stopReason` do turno anterior, recomeço com descoberta, e o
texto do prompt como **voto fraco**. Isso mede o comportamento do Kiro, não o vocabulário
do dev. Fronteiras ambíguas ficam com `confidence: low` e podem, opcionalmente, ser
desempatadas por `scripts/segment_llm.py` (opt-in, `--enable-llm-judge`). Detalhes em
[`references/task-segmentation.md`](references/task-segmentation.md).

### Passo 3 — Calcular métricas

- `scripts/metrics_deterministic.py` → 🟢 (turns, tempo de execução, tool failure,
  discovery effort, context usage, rework, alucinação intra-sessão por tarefa, rejeição de
  ferramenta, turnos abortados e — quando disponíveis — créditos). Quebra também por
  `agentMode` (vibe/spec/cli), já que Vibe e Spec custam diferente.
- `scripts/metrics_trend.py` → 🟡 (correção humana, first-pass, alucinação semântica,
  resolution efficiency).
- `scripts/semantic_eval.py` → 🟡 opcional, **OFF por padrão**, exige `--enable-llm-judge`.

A definição formal, fórmula, classe e limitações de cada métrica estão em
[`references/metric-definitions.md`](references/metric-definitions.md). **Consulte antes
de calcular** — em especial a calibragem de exit codes benignos da Tool Failure Rate.

### Passo 4 — Anonimizar

Rode `scripts/anonymize.py`: hash de session-ids, remoção de paths absolutos, truncagem
de trechos de evidência. Passo **obrigatório**. Política completa em
[`references/privacy.md`](references/privacy.md).

### Passo 5 — Snapshot e relatório (período único)

1. `scripts/snapshot.py` → congela as métricas do período em `<label>.json` (inclui as
   stats de segmentação via `--segmented`, a versão do Kiro e o canário de vocabulário).
2. `scripts/render_html.py` → recebe o **snapshot** e gera o HTML de período único,
   lendo `class` de cada métrica para aplicar o marcador 🟢/🟡 e a legenda.

Saída em diretório de trabalho **fora** de `~/.kiro/` (default: `./.harness-metrics/`,
que deve estar no `.gitignore` do workspace):

```
.harness-metrics/
├── snapshots/<label>.json
└── reports/<label>.html
```

### Passo 5b — Comparação entre períodos (opcional)

Só quando o usuário pedir explicitamente para confrontar dois períodos: gerar dois
snapshots com labels diferentes, rodar `scripts/compare.py` → `report.json` e passar esse
report ao `render_html.py`. Ver [`references/baseline-after.md`](references/baseline-after.md).

### Passo 6 — Apresentar com a distinção de confiança

Ao resumir para o usuário, sempre marque cada métrica com 🟢/🟡 e explique que as 🟡 são
tendências para comparação relativa, não valores absolutos. Exiba **n (nº de tarefas)** ao
lado de cada Δ% e sinalize quando a amostra for pequena demais para conclusão.

## Exemplos

### Relatório de um período (modo principal)
```
Analise meu uso do Kiro neste repo em agosto de 2026.
→ collect → segment → metrics(det+trend) → anonymize → snapshot(label=2026-08)
→ render_html(snapshot)  ⇒ HTML de período único
```

### Desempatar fronteiras ambíguas com LLM (opt-in)
```
Analise agosto e, nas fronteiras de tarefa ambíguas, use o LLM para desempatar.
→ ... → segment → segment_llm --enable-llm-judge → metrics → ... → render_html
(ENVIA trechos a LLM externo — ver references/privacy.md)
```

### Comparar dois períodos (opcional)
```
Compare julho com agosto neste repo.
→ dois snapshots (label=2026-07, label=2026-08) → compare → render_html(report)
```

### Só métricas determinísticas (sem tendência)
```
Quero só os números que são fato, sem estimativa.
→ metrics_deterministic apenas; render marca tudo como 🟢
```

## Referências

| Reference | Foco | Impacto |
|---|---|---|
| [`event-schema.md`](references/event-schema.md) | schema do messages.jsonl e limitações de dados | CRITICAL |
| [`metric-definitions.md`](references/metric-definitions.md) | fórmula, classe 🟢/🟡 e limitações de cada métrica | CRITICAL |
| [`task-segmentation.md`](references/task-segmentation.md) | score multi-sinal + tie-breaker LLM | HIGH |
| [`baseline-after.md`](references/baseline-after.md) | comparação entre períodos (modo opcional) | MEDIUM |
| [`privacy.md`](references/privacy.md) | política local-first e opt-in do LLM externo | CRITICAL |

Leia `event-schema.md` e `metric-definitions.md` antes de calcular qualquer coisa.
