# Metodologia Baseline → After (modo OPCIONAL)

> O modo principal da skill é o **relatório de período único**. A comparação descrita
> aqui é opcional, para quando o usuário pedir explicitamente para confrontar dois
> períodos (antes/depois de uma mudança — ex: reestruturar contexto, mudar AGENTS.md).

Objetivo: comparar objetivamente o uso do Kiro entre dois períodos e medir a evolução
das métricas.

## Mecanismo: label + snapshot (recomendado)

Data solta é frágil (tarefa cruza a meia-noite; o dia da mudança fica ambíguo). Usar:

1. **Data seleciona** as sessões do período:
   ```
   --from <ISO> --to <ISO> --label baseline
   ```
2. **Snapshot congela** as métricas calculadas num arquivo imutável `<label>.json`. A
   comparação lê os snapshots — **não recalcula**.
3. Repetir para o outro período:
   ```
   --from <ISO> --to <ISO> --label after
   ```
4. `compare.py` produz `report.json` com Δ absoluto e Δ% por métrica.

## O que o snapshot deve conter
- **versão do Kiro** (`kiroVersion`) — o que de fato detecta quebra de formato — e a
  versão da skill; `schemaVersion` é registrado só para auditoria (não confiável sozinho);
- range `from`/`to` e `label`;
- nº de sessões e nº de tarefas (com `confidence`);
- hash do input (para detectar comparação inválida);
- fórmula usada nas métricas derivadas (ex: qual variante de Resolution Efficiency);
- `unmappedActionTypes` (canário de vocabulário);
- todas as métricas com seu `class` (🟢/🟡).

## ⚠️ Comparação que atravessa upgrade do Kiro

Dois riscos ao comparar períodos separados por uma atualização do Kiro:

1. **Vocabulário de `actionType`** pode ter mudado (camel→snake). Se os dois snapshots
   têm `kiroVersion` diferente OU `unmappedActionTypes.ratio` alto, as métricas de
   descoberta/implementação não são comparáveis. `compare.py` avisa; `actions.py` mitiga.
2. **Migração v3 do CLI não é automática** e o [migration guide](https://kiro.dev/docs/cli/v3/migration-guide/)
   diz que sessões com histórico extenso de tool results "may lose some historical tool
   outputs". Comparação baseline/after que cruze esse upgrade confronta períodos com
   **fidelidade de dado diferente** — registre isso e prefira comparar dentro da mesma
   versão do Kiro.

## Regras de comparação válida
- **Mesma fórmula** nas métricas derivadas nos dois snapshots. Se diferente → recusar
  comparação (ou recalcular ambos).
- **Mesma versão de schema/skill** ou aviso explícito de incompatibilidade.
- **Comparar 🟢 com 🟢 e 🟡 com 🟡** — nunca misturar classes ao computar Δ.

## Cuidado estatístico
- Exibir **n (nº de tarefas)** ao lado de cada Δ%.
- Sinalizar quando n for pequeno (ex: < 10 tarefas) — Δ% engana com amostra baixa.
- Preferir mediana a média em métricas com cauda longa (turns, discovery).
- Não afirmar causalidade: a skill mede correlação temporal, não prova que a mudança
  causou a diferença.

## Rótulos além de baseline/after
O mecanismo aceita labels arbitrários (`--label semana-1`, `--label pos-steering`), então
serve para séries com mais de dois pontos. `compare.py` no MVP compara dois; múltiplos
pontos ficam para evolução futura.
