# Event Schema — histórico do Kiro

Documentação do armazenamento local do Kiro, levantada por inspeção (não é schema
oficial). O `Export Chat` do Kiro produz o **mesmo layout** (`session.json` +
`messages.jsonl` + `sub-executions/*.jsonl`), então esse layout é confirmado pelo export
oficial — o que o export NÃO documenta é o vocabulário de `actionType` (ver aviso abaixo).
`schemaVersion` se mostrou pouco confiável para detectar quebras; não barre por ele.

> **Aviso de estabilidade:** este formato **não é documentado oficialmente** e pode mudar
> entre versões do Kiro. Na inspeção de referência: `session.json` com
> `schemaVersion: "1.0.0"`, `dataModelVersion: 1`.

## Layout de diretórios

```
~/.kiro/
├── sessions/
│   ├── <workspace-hash>/                 # 1 bucket por workspace
│   │   └── <session-uuid>/
│   │       ├── session.json              # metadados da sessão
│   │       ├── messages.jsonl            # event log (fonte primária)
│   │       ├── snapshots/<hash>/         # snapshots de arquivos (checkpoints de edição)
│   │       └── sub-executions/           # execuções de sub-agentes (opcional)
│   └── cli/<uuid>.{json,jsonl}           # sessões do kiro-cli (v3) — normalizado por collectors_cli.py
├── session-index/<workspace-hash>.jsonl  # índice append-only {op, sessionPath, at}
└── crew/usage/tokens/<YYYY-MM-DD>.jsonl  # telemetria — SÓ do agente kirocrew (ver Limitações)
```

## `session.json`

Campos confiáveis:

| Campo | Tipo | Uso |
|---|---|---|
| `id` | string (uuid) | Identificador da sessão (anonimizar antes de expor) |
| `title` | string | Título gerado |
| `agentMode` | `"vibe"` \| `"spec"` | Segmentar por tipo de sessão |
| `workspacePaths` / `rootPaths` | string[] | Path absoluto — **remover/anonimizar** |
| `createdAt` / `lastModifiedAt` | ISO 8601 | Duração agregada da sessão |
| `modelId` | string | Modelo configurado (ex: `auto`) |
| `autopilot` | bool | Modo de autonomia |
| `status` | string | ex: `in_progress` |
| `description` | string | Pode conter texto do usuário — tratar como sensível |

## `messages.jsonl`

Cada linha: `{ id, timestamp, payload }`. `timestamp` é ISO 8601. O discriminador é
`payload.type`.

| `payload.type` | Campos-chave | Serve para |
|---|---|---|
| `user` | `content`, `source` | Prompts; detecção de correção (🟡) |
| `assistant` | `content`, `operationType`, `reasoningModelId` | Respostas; modelo real (ex: `qdev::auto`) |
| `turn_start` | `executionId` | Início de turno |
| `turn_end` | `executionId`, `stopReason` | Fim de turno (ex: `end_turn`; cancelled/failed/aborted = 🟢 dificuldade) |
| `tool_call` | `toolName`, `actionType`, `args`, `filePath`, `kind`, `toolCallId` | Ações da IA |
| `tool_result` | `success` (bool), `durationMs`, `content`, `toolCallId` | Falha, latência, saída |
| `steering_inclusion` | `documents[].id/displayName/content` | Contexto injetado (steering/AGENTS) |
| `session_metadata` | `key`, `value` | `key: "contextUsage"` → `value.usagePercentage` |
| `pending_interaction` | `interactionType`, `question`, `options` | Aprovação de ferramenta / pergunta |
| `interaction_resolved` | `outcome`, `selectedOption` | Aprovou / rejeitou (ver nota — rejeição vive em `selectedOption`) |
| `usage_summary` | `elapsedTime`, `status`, `requestIds`, `promptTurnSummaries` | **Tempo real de execução** (🟢); créditos por turno *se* `promptTurnSummaries` popular (ver nota) |
| `sub_agent_start` / `sub_agent_complete` | `executionId` | Uso de sub-agentes na tarefa |
| `ContextualHookInvoked` | `hookId`, `name`, `hookActionType`, `status` | Hooks disparados (ex: AppSec Gate) — contexto extra injetado |
| `session_event` | `category`, `context` | Ciclo de vida (ex: `category: "session_pause"` com `context.status`) |
| `tombstone` | `kind`, `effectiveFromMessageId`, `metadata` | **Sumarização/truncamento de contexto** (Kiro 1.0.395+) — pressão de contexto 🟢 |

> **`interaction_resolved` (Kiro 1.0.395+):** o campo `outcome` passou a ser sempre
> `"selected"`; a escolha real (`accept` | `always-accept` | `reject` | `deny`) vem em
> **`selectedOption`**. Ler só `outcome` zera as rejeições nas versões novas. A skill lê
> `selectedOption` (rejeição = correção humana 🟢; `always-accept` é contado à parte como
> sinal de fadiga de aprovação).

> **`tombstone` (Kiro 1.0.395+):** quando o Kiro sumariza o contexto, grava
> `{kind: "summarization", effectiveFromMessageId, metadata: {truncatedMessageCount, truncatedAt}}`.
> É um sinal 🟢 direto de pressão de contexto (mais confiável que o `contextUsage` amostrado):
> `metrics_deterministic.py` conta as sumarizações por sessão e soma as mensagens descartadas.

> **`usage_summary.elapsedTime`** (ms) é uma medida direta e confiável de tempo de
> execução por turno/tarefa — melhor que só o delta de timestamps. Usar em Resolution
> Efficiency e Turns.
>
> **`promptTurnSummaries`**: em versões recentes do Kiro vem **populado** (observado em
> 304/310 `usage_summary` numa máquina real), com entradas `{unit: "credit", usage, usedTools}`.
> É a via para **créditos por turno/sessão de IDE**. Nem toda versão popula; quando presente,
> `metrics_deterministic.py` soma `usage` (unit=credit). NÃO validado contra o "Est. Credits
> Used" da UI — tratar como aproximação. Tokens brutos (input/output) seguem indisponíveis.

### `actionType` observados em `tool_call` — DOIS VOCABULÁRIOS

⚠️ **Crítico:** o Kiro renomeou os `actionType` de **camelCase** (`readFiles`, `runCommand`)
para **snake_case** (`read_files`, `run_command`) por volta do 1.0.0, mantendo
`schemaVersion: "1.0.0"` nos dois lados. Sets fixos num só vocabulário perdem ~80% dos
tool_calls e chegam a **inverter** o veredito de Context Discovery Effort. Confirmado na
1.0.395: `run_command` e `runCommand` coexistem na MESMA sessão.

Por isso a classificação vive em **`scripts/actions.py`**, que trata os dois vocabulários
como aliases e normaliza tudo. O que não casar cai num fallback por verbo (get/read/list →
descoberta; create/push/update → other, cobre servidores MCP); só o irreconhecível vira
`unknown` e é contabilizado pelo canário `unmappedActionTypes` (avisa quando muda de novo).

Exemplos observados: `readFiles`/`read_files`, `runCommand`/`run_command`, `search`,
`grep_search`, `readCode`/`read_code`, `web_fetch`, `getDiagnostics`, `write`/`fs_write`,
`str_replace`, `create`, `delete`, `mcp`, `mcp_github_*`, `controlProcess`,
`getProcessOutput`, `createHook`, `update_session_information`.

Mapeamento para categorias de métrica (ver `actions.py` para a lista completa de aliases):
- **Descoberta:** leituras/buscas (`read_files`, `search`, `grep_search`, `web_fetch`, `mcp`,
  `read_code`, `get_diagnostics`, `getProcessOutput`) + shell de leitura (grep/find/ls/cat/git status…).
- **Implementação:** `write`, `str_replace`, `create`, `delete`, `append`, rename/move.
- **Outros (não contam no ratio):** hooks, `controlProcess`, e MCP de mutação (push/create/merge).

### `_meta.kiro.checkpoint`
Em `tool_result` de edições, aparece `_meta.kiro.checkpoint` com `snapshotId` e
`sessionId`. Base para detectar **reverts/restauração** (Rework 🟢).

## Correlação de tool_call ↔ tool_result
Pelo `toolCallId`. Um `tool_result.success === false` indica falha da ferramenta — ver
calibragem de exit codes benignos em `metric-definitions.md`.

## Consumo — créditos e tempo (🟢 quando presentes)

- **Créditos por sessão:** `usage_summary.promptTurnSummaries[].usage` (unit=credit),
  somado por `metrics_deterministic.py`. Aproximação (não batida contra a UI).
- **Tempo real:** `usage_summary.elapsedTime` (ms) por turno — mediana reportada.
- **Rollup de time:** para custo por usuário/time, a fonte oficial é o **CSV diário do
  Kiro Enterprise no S3** (`Date, UserId, Client_Type, Credits_Used, Chat_Conversations,
  Total_Messages`, + contagem por modelo). A skill local é complementar (tool calls,
  retrabalho, alucinação, esforço de descoberta).

## Limitações de dados (CRÍTICO)

1. **Tokens brutos (input/output) por sessão de IDE: indisponíveis.** Só há créditos
   agregados via `promptTurnSummaries` (acima). O store `crew/usage/tokens/` cobre apenas
   o agente `kirocrew` (surface cron/dashboard/subagent), com input/output zerados e sem
   linkagem a session-id de IDE.
2. **`contextUsage` é amostrado**, não contínuo — bom para tendência, ruim para precisão
   fina. Interpolar com cautela. (Para pressão de contexto direta, prefira `tombstone`.)
3. **`tool_result.success` de `execute_bash` reflete exit code**, que tem falsos
   positivos (ex: `rmdir` de pasta ausente, exit 1 de shell vazio). Requer allowlist.
4. **Estado do repo ≠ estado da sessão.** Verificação de path contra o repo atual é
   frágil; a contradição **intra-sessão** (afirmação depois desmentida por um
   `tool_result` no mesmo log) é muito mais confiável.
5. **Sessões CLI têm outro formato** — normalizadas por `collectors_cli.py` (ver abaixo).
6. **"Tarefa" não é explícita** — precisa ser inferida (ver `task-segmentation.md`).

## Sessões CLI (`~/.kiro/sessions/cli/`)

O Kiro CLI grava um par por sessão: `<uuid>.json` (metadados) + `<uuid>.jsonl` (eventos).
Formato diferente do IDE — normalizado por `collectors_cli.py` para o mesmo shape.

### Metadados (`<uuid>.json`)
`session_id`, `cwd`, `created_at`, `updated_at`, `title`, `session_created_reason`.

### Eventos (`<uuid>.jsonl`)
Linhas `{version, kind, data}`. `kind` ∈ `Prompt`, `AssistantMessage`, `ToolResults`,
`Clear`. Este é o formato **v3** (o `.json` + `.jsonl`); a página `session-management` da
doc ainda descreve o SQLite v1/v2 e está desatualizada.

`Clear` (o `/clear`) zera o contexto — o adaptador o traduz em fronteira **dura** de tarefa
(`session_event.hardBoundary`), forçando o segmentador a abrir nova tarefa no próximo prompt.

`exit_status` do CLI tem o formato `exit status: 0` — a regra de sucesso casa por
`"status: 0"`.

### Mapeamento CLI → IDE (feito pelo adaptador)

| CLI kind | vira | observações |
|---|---|---|
| `Prompt` | `user` (+ `turn_start` sintético) | `content` é lista de blocos `{kind:text}` |
| `AssistantMessage` | `assistant` + `tool_call` (por bloco `toolUse`) | `toolUse.name` mapeado para `actionType` |
| `ToolResults` | `tool_result` (por bloco `toolResult`) | `success` extraído de `exit_status` / `status` |
| `Clear` | `session_event` (hardBoundary) | `/clear` — fronteira dura de tarefa |

`turn_end` sintético é inserido ao fim de cada turno para a contagem de turnos funcionar.

### Limitações do CLI (afetam métricas)
- **Sem timestamp por evento** → gap temporal (sinal de peso 35% da segmentação) fica
  indisponível; `timestamp=None` e o gap vira sinal neutro. Segmentação de sessões CLI é
  menos precisa.
- **Sem `stopReason` real nem `contextUsage`** → Context Usage não é medido para CLI.
- **`durationMs` ausente** nos tool_results.
- **Migração v3 não é automática** e pode perder histórico de tool results — relevante para
  comparação baseline/after que cruze o upgrade (ver `baseline-after.md`).

### Filtro de automação (importante)
Muitas sessões CLI são de **automação** (`session_created_reason` ∈ subagent, cron, hook,
heartbeat) — geradas pelo agente de background (kirocrew), NÃO por uso interativo de dev.
Por padrão o adaptador **pula** essas sessões (só conta CLI interativo). Use
`--include-automation` para incluí-las. Cada sessão carrega `surface: "ide" | "cli"` para
o report distinguir a origem.
