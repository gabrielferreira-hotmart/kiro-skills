# Advanced Queries

## Aggregations

### Top errors grouped by message

```bash
curl -sk "ENDPOINT/INDEX/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "must": [
          {"term": {"level.keyword": "ERROR"}},
          {"range": {"timestamp": {"gte": "now-6h"}}}
        ]
      }
    },
    "size": 0,
    "aggs": {
      "error_messages": {"terms": {"field": "message.keyword", "size": 20}}
    }
  }' | jq '.aggregations.error_messages.buckets'
```

### Status distribution with time histogram

```bash
curl -sk "ENDPOINT/INDEX/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "must": [
          {"match_phrase": {"mdc.uri": "/PATH"}},
          {"range": {"timestamp": {"gte": "now-1h"}}}
        ]
      }
    },
    "size": 0,
    "aggs": {
      "by_status": {"terms": {"field": "mdc.response-status.keyword", "size": 10}},
      "by_pod": {"terms": {"field": "log_summary.kubernetes.pod_name.keyword", "size": 20}},
      "over_time": {
        "date_histogram": {"field": "timestamp", "fixed_interval": "5m"},
        "aggs": {"errors": {"filter": {"term": {"level.keyword": "ERROR"}}}}
      }
    }
  }' | jq '.aggregations'
```

### List all active facilities

```bash
curl -sk "ENDPOINT/prd_log_docker_*_log_*/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "size": 0,
    "query": {"range": {"timestamp": {"gte": "now-1h"}}},
    "aggs": {"facilities": {"terms": {"field": "facility.keyword", "size": 500}}}
  }' | jq '.aggregations.facilities.buckets[].key'
```

## Scroll API (Pagination)

Use for extracting more than 10,000 results:

```bash
# Initial request
RESPONSE=$(curl -sk "ENDPOINT/INDEX/_search?scroll=2m" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {"term": {"level.keyword": "ERROR"}},
    "size": 1000,
    "sort": [{"timestamp": {"order": "desc"}}]
  }')

echo "$RESPONSE" | jq '.hits.hits[]._source'
SCROLL_ID=$(echo "$RESPONSE" | jq -r '._scroll_id')

# Subsequent pages
curl -sk "ENDPOINT/_search/scroll" \
  -H 'Content-Type: application/json' \
  -d "{\"scroll\": \"2m\", \"scroll_id\": \"$SCROLL_ID\"}" | jq '.hits.hits[]._source'
```

## Absolute Time Range

```json
{"range": {"timestamp": {"gte": "2026-07-06T10:00:00.000Z", "lte": "2026-07-06T11:00:00.000Z"}}}
```

## Full-Text Message Search

```json
// Partial match (tokenized)
{"match": {"message": "connection timeout"}}

// Exact phrase match
{"match_phrase": {"message": "Connection refused"}}

// Exclude noise
"must_not": [
  {"match_phrase": {"message": "health-check"}},
  {"match_phrase": {"message": "actuator"}}
]
```

## Combining Multiple Filters

```json
{
  "query": {
    "bool": {
      "must": [
        {"term": {"level.keyword": "ERROR"}},
        {"match_phrase": {"mdc.uri": "/api/v2/products"}},
        {"range": {"timestamp": {"gte": "now-2h"}}}
      ],
      "must_not": [
        {"term": {"mdc.response-status.keyword": "404"}}
      ],
      "should": [
        {"match_phrase": {"message": "timeout"}},
        {"match_phrase": {"message": "connection refused"}}
      ],
      "minimum_should_match": 1
    }
  }
}
```

## Field Discovery

List all fields in an index:

```bash
curl -sk "ENDPOINT/INDEX/_mapping" | jq 'to_entries[0].value.mappings.properties | keys'
```

Show MDC field types:

```bash
curl -sk "ENDPOINT/INDEX/_mapping" | jq 'to_entries[0].value.mappings.properties.mdc.properties | to_entries[] | {(.key): .value.type}'
```
