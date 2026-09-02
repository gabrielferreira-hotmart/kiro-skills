#!/usr/bin/env bash
# kibana-datahub.sh — Busca eventos DataHub no Elasticsearch
# Uso: ./scripts/kibana-datahub.sh search [flags]
#      ./scripts/kibana-datahub.sh discover <fields|sample|mappings> [--index pattern]
#      ./scripts/kibana-datahub.sh systems [--search <filtro>]
set -euo pipefail

ES_URL="https://vpc-es-datahub-2021-07-10-zi76rgukjhaaawzvk53rubikfy.us-east-1.es.amazonaws.com"
DEFAULT_INDEX="*datahub*"

# --- Subcomando systems ---
do_systems() {
  local search=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --search) search="$2"; shift 2 ;;
      *) echo "Flag desconhecida: $1" >&2; exit 1 ;;
    esac
  done

  local response
  response=$(curl -s -X POST "$ES_URL/$DEFAULT_INDEX/_search" \
    -H 'Content-Type: application/json' \
    -d '{"size":0,"aggs":{"systems":{"terms":{"field":"system.keyword","size":500}}}}')

  if [[ -n "$search" ]]; then
    echo "$response" | jq -r --arg s "$search" \
      '.aggregations.systems.buckets[] | select(.key | test($s; "i")) | "\(.key)\t\(.doc_count)"' \
      | column -t -s $'\t'
  else
    echo "$response" | jq -r \
      '.aggregations.systems.buckets[] | "\(.key)\t\(.doc_count)"' \
      | column -t -s $'\t'
  fi
}

# --- Subcomando discover ---
do_discover() {
  local action="${1:-fields}"
  shift || true
  local index="$DEFAULT_INDEX"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --index) index="$2"; shift 2 ;;
      *) shift ;;
    esac
  done

  case "$action" in
    fields)
      curl -s "$ES_URL/$index/_mapping" | jq '[path(.. | .type? // empty) | .[:-1] | join(".")] | sort'
      ;;
    sample)
      curl -s -X POST "$ES_URL/$index/_search" \
        -H 'Content-Type: application/json' \
        -d '{"query":{"match_all":{}},"size":3,"sort":[{"timestamp":{"order":"desc"}}]}' \
        | jq '.hits.hits[]._source'
      ;;
    mappings)
      curl -s "$ES_URL/$index/_mapping" | jq '.'
      ;;
    *) echo "Uso: $0 discover <fields|sample|mappings>" >&2; exit 1 ;;
  esac
}

# --- Subcomando search ---
do_search() {
  local must_clauses=()
  local must_not_clauses=()
  local size=10
  local index="$DEFAULT_INDEX"
  local fields=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --system)       must_clauses+=("{\"term\":{\"system.keyword\":\"$2\"}}"); shift 2 ;;
      --event-type)   must_clauses+=("{\"term\":{\"event_type.keyword\":\"$2\"}}"); shift 2 ;;
      --entity)       must_clauses+=("{\"term\":{\"entity.keyword\":\"$2\"}}"); shift 2 ;;
      --action)       must_clauses+=("{\"term\":{\"action.keyword\":\"$2\"}}"); shift 2 ;;
      --product-id)   must_clauses+=("{\"term\":{\"event.product.id\":$2}}"); shift 2 ;;
      --contains)     must_clauses+=("{\"query_string\":{\"default_field\":\"*\",\"query\":\"*$2*\"}}"); shift 2 ;;
      --custom)
        local field="${2%%=*}" value="${2#*=}"
        if [[ "$value" =~ ^[0-9]+$ ]]; then
          must_clauses+=("{\"term\":{\"$field\":$value}}")
        else
          must_clauses+=("{\"term\":{\"$field\":\"$value\"}}")
        fi
        shift 2 ;;
      --exclude)
        local efield="${2%%=*}" evalue="${2#*=}"
        if [[ "$evalue" =~ ^[0-9]+$ ]]; then
          must_not_clauses+=("{\"term\":{\"$efield\":$evalue}}")
        else
          must_not_clauses+=("{\"term\":{\"$efield\":\"$evalue\"}}")
        fi
        shift 2 ;;
      --last)         must_clauses+=("{\"range\":{\"timestamp\":{\"gte\":\"now-$2\"}}}"); shift 2 ;;
      --from)
        local from="$2"; shift 2
        local to="now"
        if [[ "${1:-}" == "--to" ]]; then to="$2"; shift 2; fi
        must_clauses+=("{\"range\":{\"timestamp\":{\"gte\":\"$from\",\"lte\":\"$to\"}}}")
        ;;
      --to)           must_clauses+=("{\"range\":{\"timestamp\":{\"lte\":\"$2\"}}}"); shift 2 ;;
      --size)         size="$2"; shift 2 ;;
      --index)        index="$2"; shift 2 ;;
      --fields)       fields="$2"; shift 2 ;;
      *) echo "Flag desconhecida: $1" >&2; exit 1 ;;
    esac
  done

  # Montar query
  local query
  if [[ ${#must_clauses[@]} -eq 0 && ${#must_not_clauses[@]} -eq 0 ]]; then
    query='{"match_all":{}}'
  else
    local must_json="[]" must_not_json="[]"
    if [[ ${#must_clauses[@]} -gt 0 ]]; then
      must_json=$(printf '%s\n' "${must_clauses[@]}" | jq -s '.')
    fi
    if [[ ${#must_not_clauses[@]} -gt 0 ]]; then
      must_not_json=$(printf '%s\n' "${must_not_clauses[@]}" | jq -s '.')
    fi
    query=$(jq -cn --argjson must "$must_json" --argjson must_not "$must_not_json" \
      '{bool: (if ($must | length) > 0 then {must: $must} else {} end + if ($must_not | length) > 0 then {must_not: $must_not} else {} end)}')
  fi

  # Montar body
  local body
  if [[ -n "$fields" ]]; then
    local fields_json
    fields_json=$(echo "$fields" | tr ',' '\n' | jq -R . | jq -s '.')
    body=$(jq -cn --argjson q "$query" --argjson size "$size" --argjson src "$fields_json" \
      '{query: $q, size: $size, sort: [{"timestamp": {"order": "desc"}}], _source: $src}')
  else
    body=$(jq -cn --argjson q "$query" --argjson size "$size" \
      '{query: $q, size: $size, sort: [{"timestamp": {"order": "desc"}}]}')
  fi

  # Executar
  local response
  response=$(curl -s -X POST "$ES_URL/$index/_search" \
    -H 'Content-Type: application/json' \
    -d "$body")

  # Verificar erro
  if echo "$response" | jq -e '.error' >/dev/null 2>&1; then
    echo "Erro ES:" >&2
    echo "$response" | jq '.error' >&2
    exit 1
  fi

  # Output
  local total took
  total=$(echo "$response" | jq '.hits.total.value // .hits.total')
  took=$(echo "$response" | jq '.took')

  # Aviso de 0 resultados
  if [[ "$total" -eq 0 ]]; then
    echo "⚠️  Nenhum resultado encontrado (index: $index)." >&2
    echo "   Possíveis causas:" >&2
    echo "   - O system ou event_type pode estar incorreto" >&2
    echo "   - Use 'kibana-datahub.sh systems' para listar systems disponíveis" >&2
    echo "   - O campo de product_id pode variar — use --custom campo=valor" >&2
    echo "   - Tente ampliar o período com --last" >&2
  fi

  echo "$response" | jq --argjson total "$total" --argjson took "$took" \
    '{total_hits: $total, took_ms: $took, results: [.hits.hits[]._source]}'
}

# --- Main ---
case "${1:-}" in
  search)   shift; do_search "$@" ;;
  discover) shift; do_discover "$@" ;;
  systems)  shift; do_systems "$@" ;;
  *)
    echo "Uso: $0 <search|discover|systems> [args]"
    echo ""
    echo "  search [flags]                          Buscar eventos DataHub"
    echo "  discover <fields|sample|mappings>       Descobrir estrutura do índice"
    echo "  systems [--search <filtro>]             Listar systems disponíveis"
    echo ""
    echo "Flags de search: --system, --event-type, --entity, --action,"
    echo "  --product-id, --contains, --custom, --exclude, --last,"
    echo "  --from, --to, --size, --index, --fields"
    exit 1
    ;;
esac
