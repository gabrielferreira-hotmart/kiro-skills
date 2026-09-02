# Club Services — Dedicated Cluster

The `vpc-es-club-logs` cluster contains logs from Club core APIs.
All other Club applications send logs to the general production cluster (`vpc-logs-2020`).

The list of services in this cluster is dynamic — services can be added or removed at any time.

## Endpoint

```
https://vpc-es-club-logs-mb2o4255mspnp6abkd7rnw3uxy.us-east-1.es.amazonaws.com
```

## Decision Rule

If the app name starts with `api-club-`, try the Club dedicated cluster first.
If the index doesn't exist or returns 0 hits, fall back to the general production cluster.

## Discovering Services

List all services currently in the Club cluster:

```bash
curl -sk 'https://vpc-es-club-logs-mb2o4255mspnp6abkd7rnw3uxy.us-east-1.es.amazonaws.com/_cat/indices/prd_log_docker_*?h=index' \
  | sed 's/_2026_[0-9_]*//' | sort -u
```

## Example

```bash
curl -sk "https://vpc-es-club-logs-mb2o4255mspnp6abkd7rnw3uxy.us-east-1.es.amazonaws.com/prd_log_docker_api_club_content_log_*/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "must": [
          {"term": {"level.keyword": "ERROR"}},
          {"range": {"timestamp": {"gte": "now-1h"}}}
        ]
      }
    },
    "size": 10,
    "sort": [{"timestamp": {"order": "desc"}}]
  }' | jq '.hits.hits[]._source'
```
