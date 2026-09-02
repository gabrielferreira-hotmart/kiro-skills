---
name: "delta-release"
description: "Dispara o workflow de Delta Release do sparkle-ios no GitHub Actions. Gera um build incremental e envia para o TestFlight (Staging ou Production)."
keywords: ["delta", "release", "deploy", "testflight", "staging", "production", "workflow", "github-actions", "sparkle", "cd"]
---

# Sparkle iOS — Delta Release

## O que é

O Delta Release é um build incremental do app Sparkle (variante "Delta") que pode ser disparado manualmente para enviar uma versão ao TestFlight. É usado para testar branches específicas em ambiente Staging ou publicar em Production sem precisar de um ciclo de release completo.

## Parâmetros

| Parâmetro | Obrigatório | Valores | Descrição |
|-----------|-------------|---------|-----------|
| **branch** (ref) | ✅ | qualquer branch existente | Branch que será usada para o build |
| **process_environment** | ✅ | `Staging` ou `Production` | Ambiente de destino |

## Workflow

### 1. Perguntar ao usuário

Quando o usuário pedir para disparar um delta release, coletar:

1. **Qual branch?** — nome exato da branch (ex: `develop`, `feature/LEX-4521`, `MCG-2215`)
2. **Qual ambiente?** — Staging (padrão) ou Production

Se o usuário não especificar o ambiente, usar **Staging** como padrão.

### 2. Disparar o workflow

Usar a tool `mcp_github_trigger_workflow` com os seguintes parâmetros:

```
owner: Hotmart-Org
repo: sparkle-ios
workflow_id: "application-cd-delta-release.yml"
ref: <branch informada pelo usuário>
inputs: { "process_environment": "<Staging ou Production>" }
```

Exemplo concreto:

```json
{
  "owner": "Hotmart-Org",
  "repo": "sparkle-ios",
  "workflow_id": "application-cd-delta-release.yml",
  "ref": "feature/LEX-4521",
  "inputs": {
    "process_environment": "Staging"
  }
}
```

### 3. Confirmar o disparo

Após disparar, informar ao usuário:
- ✅ Workflow disparado com sucesso
- Branch: `<branch>`
- Ambiente: `<environment>`
- Link: `https://github.com/Hotmart-Org/sparkle-ios/actions/workflows/192465403`

### 4. Acompanhar (opcional)

Se o usuário quiser acompanhar o status, usar `mcp_github_list_workflow_runs` com:

```
owner: Hotmart-Org
repo: sparkle-ios
workflow_id: 192465403
per_page: 1
branch: <branch>
```

## Detalhes técnicos

- **Workflow file**: `.github/workflows/application-cd-delta-release.yml`
- **Workflow ID**: `192465403`
- **App identifier**: `com.hotmart.hifire.beta`
- **Build config Staging**: `Release-Delta`
- **Build config Production**: `Release`
- **iXGuard**: Desabilitado para Delta
- **Upload destino**: TestFlight (App Store Connect)
- **Notificações**: Google Chat (início, info, sucesso/erro)
- **Tempo médio**: ~25-35 minutos

## Validações antes de disparar

1. **Confirmar com o usuário** antes de disparar (é uma ação que gera build e upload)
2. Se o ambiente for **Production**, alertar que o build será publicado para produção
3. Verificar se a branch existe (o workflow falhará se a branch não existir)

## Exemplos de uso

- "Dispara um delta release da branch develop em staging"
- "Faz um delta release da MCG-2215 pra staging"
- "Gera um delta da feature/LEX-4521 em production"
- "Roda o delta release na branch atual"

## Monitoramento de runs anteriores

Para listar as últimas execuções:

```
mcp_github_list_workflow_runs:
  owner: Hotmart-Org
  repo: sparkle-ios
  workflow_id: 192465403
  per_page: 5
```

Para ver detalhes de uma run específica:

```
mcp_github_get_workflow_run_details:
  owner: Hotmart-Org
  repo: sparkle-ios
  run_id: <run_id>
```
