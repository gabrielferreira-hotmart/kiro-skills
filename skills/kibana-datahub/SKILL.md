---
name: "kibana-datahub"
description: "Busca de eventos DataHub no Elasticsearch via curl. Suporta qualquer system/event_type. Index padrão: *datahub*"
keywords: ["kibana", "datahub", "elasticsearch", "eventos", "cdc", "domain-events"]
---

# Kibana DataHub — Eventos de Domínio

> Cluster ES: https://vpc-es-datahub-2021-07-10-zi76rgukjhaaawzvk53rubikfy.us-east-1.es.amazonaws.com
> Index padrão: `*datahub*`
> Auth: Nenhuma (acesso via VPC/VPN)

## Dependências

- **VPN** ativa (acesso ao cluster ES via VPC)
- `curl` instalado
- `jq` instalado (formatação do output JSON)
- Bash 3.2+ (compatível com macOS nativo)

## Quick Start

```bash
# Listar todos os systems disponíveis
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh systems

# Filtrar systems por nome
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh systems --search product

# Eventos de um system na última hora
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh search --system api_product_web --last 1h

# Eventos por event_type
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh search --event-type api_product_web_product_update --last 6h

# Eventos de um produto específico
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh search --product-id 7324260 --last 1d

# Filtro por entidade e ação
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh search --entity product --action update --last 1h

# Filtro customizado (campo ES direto)
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh search --custom "event.productId=7715576" --last 1d

# Excluir eventos de uma ação
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh search --system api_product_web --exclude "action.keyword=metrify" --last 1h

# Campos específicos no output
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh search --system api_product_web --fields "timestamp,event_type,event.product.id" --size 5

# Descobrir campos disponíveis
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh discover fields

# Ver amostras de eventos
~/.kiro/skills/kibana-datahub/scripts/kibana-datahub.sh discover sample
```

## Script — `kibana-datahub.sh`

### Subcomandos

| Subcomando | Descrição |
|------------|-----------|
| `search [flags]` | Buscar eventos com filtros |
| `discover <fields\|sample\|mappings>` | Descobrir estrutura do índice |
| `systems [--search <filtro>]` | Listar systems disponíveis (com contagem) |

### Flags de `search`

| Flag | Descrição | Exemplo |
|------|-----------|---------|
| `--system` | Sistema que publicou o evento | `api_product_web` |
| `--event-type` | Tipo do evento | `api_product_web_product_update` |
| `--entity` | Entidade do evento | `product`, `purchase` |
| `--action` | Ação do evento | `create`, `update`, `delete`, `metrify` |
| `--product-id` | ID do produto (usa `event.product.id`) | `7324260` |
| `--contains` | Busca textual no payload (query_string) | `timeout` |
| `--custom` | Filtro ES direto (campo=valor) | `event.productId=7715576` |
| `--exclude` | Excluir por campo=valor (must_not) | `action.keyword=metrify` |
| `--last` | Período relativo | `5h`, `30m`, `1d` |
| `--from` | Data início ISO | `2026-05-13T16:00:00.000Z` |
| `--to` | Data fim ISO | `2026-05-13T17:00:00.000Z` |
| `--size` | Quantidade de resultados (default: 10) | `20` |
| `--index` | Índice ES (override do padrão) | `datahub-product-*` |
| `--fields` | Campos específicos no output (comma-separated) | `timestamp,event_type` |

## Estrutura de Dados

### Campos Universais (todos os eventos)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `timestamp` | date | Data/hora do evento (ISO 8601) |
| `system` | keyword | Sistema que publicou o evento |
| `event_type` | keyword | Tipo do evento (identifica o schema) |
| `action` | keyword | Ação: `create`, `update`, `delete`, `metrify` |
| `entity` | keyword | Entidade de domínio do evento |
| `transaction_date` | date | Data da transação de negócio |
| `event` | object | Payload do evento (estrutura varia por system/event_type) |

## Formato de Output

O script retorna JSON estruturado:

```json
{
  "total_hits": 15,
  "took_ms": 800,
  "results": [
    {
      "system": "api_product_web",
      "event_type": "api_product_web_product_update",
      "entity": "product",
      "action": "update",
      "event": { "product": { "id": 7324260 } },
      "timestamp": "2026-05-28T12:00:00.000Z"
    }
  ]
}
```

## Query ES Avançada (curl direto)

Para queries que o script não cobre (agregações, nested, etc.):

```bash
curl -s -X POST \
  'https://vpc-es-datahub-2021-07-10-zi76rgukjhaaawzvk53rubikfy.us-east-1.es.amazonaws.com/*datahub*/_search' \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "must": [
          {"term": {"system.keyword": "api_product_web"}},
          {"term": {"action.keyword": "update"}},
          {"range": {"timestamp": {"gte": "now-1h"}}}
        ]
      }
    },
    "size": 20,
    "sort": [{"timestamp": {"order": "desc"}}]
  }' | jq '.hits.hits[]._source'
```
