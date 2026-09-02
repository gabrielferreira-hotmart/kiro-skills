# Definições de métrica

Cada métrica declara `class`: 🟢 `deterministic` (fato reprodutível) ou 🟡 `trend`
(indicador semântico, comparação relativa). A classe viaja no JSON e a apresentação só
reflete.

Convenção: "tarefa" = unidade inferida pela segmentação (ver `task-segmentation.md`).

---

## 🟢 Determinísticas

### Turns to Resolution
**O que:** número de turnos (`turn_start`→`turn_end`) entre o primeiro prompt de uma
tarefa e sua resolução.
**Fórmula:** `count(turn_end no intervalo da tarefa)`.
**Agregação:** média e mediana por tarefa, por período.
**Limitações:** depende da qualidade da segmentação. Um turno pode conter várias tools.

### Tool Failure Rate
**O que:** fração de tool calls que falharam.
**Fórmula:** `falhas / total_tool_results`, onde falha = `success === false` **e não**
casa a allowlist de exit codes benignos.
**Calibragem (obrigatória):** para `execute_bash`, ignorar como falha:
- `rmdir`/`rm` com "No such file or directory" / "Directory not empty" quando o objetivo
  já foi atingido;
- exit code de prompt de shell vazio (output só com prompt, sem comando real);
- `git`/`grep` que retornam exit ≠ 0 por "nenhum resultado" (ex: grep sem match).
Registrar ambos: **bruto** (todo `success:false`) e **calibrado**. Expor o calibrado como
principal e o bruto como nota.
**Limitações:** allowlist é heurística de calibragem; documentar os padrões aplicados.

### Context Discovery Effort
**O que:** esforço de descoberta de contexto vs implementação.
**Fórmula:** `ações_descoberta / ações_implementacao` (ratio) e também contagem absoluta
de leituras/buscas antes da primeira ação de implementação da tarefa.
**Descoberta:** `readFiles`, `remote_web_search`, `webFetch`, `mcp`, `runCommand` de
leitura (grep/find/ls/cat/wc). **Implementação:** `write`, `replace`, `create`, `delete`.
**Sinais extras:** buscas repetidas pelo mesmo termo/arquivo; tempo até a primeira ação
efetiva (delta de timestamp).
**Limitações:** classificar `runCommand` exige parse do comando; um comando pode ser
ambíguo (ex: `sed` lê e escreve).

### Context Usage
**O que:** uso da janela de contexto.
**Fórmula:** série de `session_metadata.contextUsage.usagePercentage`; reportar
média, pico e distribuição por período.
**Limitações:** amostrado, não contínuo. Não é token count.

### Rework Rate
**O que:** retrabalho sobre a mesma implementação.
**Fórmula:** sinais determinísticos por tarefa —
- edições repetidas no mesmo `filePath` (> 1 `write`/`replace` no mesmo arquivo dentro da
  tarefa, após já ter sido "concluído");
- reverts/restauração de checkpoint (via `_meta.kiro.checkpoint`);
- comandos idênticos re-executados após falha.
**Agregação:** eventos de rework por tarefa.
**Limitações:** edição repetida legítima (refino incremental planejado) conta como
rework; é um sinal, não um veredito.

### Hallucination Evidence — intra-sessão
**O que:** afirmação da IA contradita por uma tool **no mesmo log**.
**Fórmula:** casar afirmação em `assistant.content` sobre existência de path/arquivo com
`tool_result` subsequente que retorna "No such file" / "did not match" / erro de path.
**Por que é 🟢:** a contradição está inteiramente dentro do log — não depende do estado
atual do repo.
**Limitações:** cobre path/arquivo; símbolos (classe/método) exigem LSP/parse e ficam
fora do MVP. Só captura alucinações que geraram uma tool subsequente.

---

## 🟡 Tendência

> Todas abaixo envolvem interpretação. Apresentar como **direção/estimativa**, nunca como
> valor absoluto. Sempre exibir n e sinalizar amostra pequena.

### Human Correction Rate
**O que:** intervenções do usuário para corrigir entendimento/direção.
**Abordagem:** classificar `user` messages pós-resposta como correção. Não depender de
frases literais; combinar sinais: negação + referência ao que a IA acabou de fazer,
pedido de reverter/refazer, correção factual. Frases-âncora multilíngues como sinal
fraco, não regra.
**Fórmula:** `correções / tarefas`.
**Limitações:** sarcasmo, correção implícita, variação de idioma. Falso negativo alto.

### First Pass Resolution
**O que:** % de tarefas resolvidas sem correção/rework após a 1ª entrega.
**Fórmula:** `tarefas sem (correção 🟡 nem rework 🟢) após primeira resposta / total`.
**Nota:** consome um sinal 🟡 (correção) → herda classe 🟡.
**Limitações:** "resolução" é inferida; ausência de correção ≠ sucesso garantido.

### Hallucination Evidence — semântica
**O que:** usuário afirma depois que a implementação partiu de entendimento incorreto.
**Abordagem:** detectar correção factual do usuário sobre algo que a IA afirmou. Opcional:
judge via LLM externo (`--enable-llm-judge`, OFF por padrão) com rubric fixa exigindo
citação da evidência (turno + linha).
**Limitações:** subjetivo; risco de viés (ver `privacy.md` sobre LLM). Usar modelo
diferente do que gerou a sessão se ativar o judge.

### Resolution Efficiency
**O que:** métrica derivada aproximando **resultado / esforço**.
**Alternativas propostas (não fixar ainda):**
- `A`: `first_pass ÷ (turns_norm + correções + falhas + rework)` — penaliza esforço.
- `B`: score composto ponderado, pesos configuráveis, normalizado 0–1.
- `C`: sucesso_estimado × (1 − esforço_normalizado).
Escolher após estabilizar as bases; expor a fórmula usada no relatório.
**Classe:** 🟡 (consome inputs 🟡).
**Limitações:** sensível aos pesos; comparar só entre snapshots com a mesma fórmula.

---

## Regra de herança de classe
Qualquer métrica derivada que consuma ao menos um input 🟡 é 🟡. Só é 🟢 se **todos** os
inputs forem 🟢.
