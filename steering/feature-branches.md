---
inclusion: always
---

# Feature Branches Workflow

## Estrutura de branches

O projeto trabalha com feature branches hierárquicas:

1. **Branch da história (feature pai)**: `feature/{TASK_PAI}` — criada a partir de `develop`
   - Exemplo: `feature/MCG-2195`

2. **Branch da subtask**: `{TASK_ID}` — criada a partir da feature branch pai
   - Exemplo: `MCG-2215` (criada a partir de `feature/MCG-2195`)

## Fluxo de PR

- PRs de subtasks devem ser abertos **para a feature branch pai** (não para develop)
  - Exemplo: PR de `MCG-2215` → `feature/MCG-2195`
- O PR da feature branch pai será aberto para `develop` quando todas as subtasks estiverem prontas

## Regras

- Sempre verificar se a feature branch pai já existe antes de criar
- Subtasks sempre derivam da feature branch pai, nunca de develop diretamente
- Ao criar PR, usar a feature branch pai como base (não develop)

## Branch Naming

- Nomear branches usando o Jira task ID (ex: `MCG-1960`, `CAA-5190`, `CTC-578`)
- Não adicionar prefixos como `feature/` ou `fix/` a menos que o usuário peça
- Sempre criar a partir de `develop` a menos que explicitamente dito o contrário
