---
name: "application-logs"
description: "Search and analyze Hotmart application logs in Elasticsearch clusters via curl. Supports production, staging, and Club. Use when the user asks to investigate errors, trace requests, search logs by trace ID, analyze latency, debug 500s, check staging logs, or find logs from any Hotmart service."
keywords: ["kibana", "application-logs", "elasticsearch", "errors", "tracing", "latency", "production", "staging", "club"]
---

# Application Logs

Search Hotmart application logs via Elasticsearch clusters using curl.

## Example Prompts

These are examples of user requests this skill handles:

- "show me errors from api-product-review in the last hour"
- "trace request 6a505c3a3e7d20c3883f4b2adb873f9a"
- "what's the p95 latency on /v2/products in api-sparkle-products?"
- "search logs for api-hotpay with status 500 in the last 30 minutes"
- "find logs from staging for api-checkout-data with level ERROR"
- "show me errors from api-club-content in the last 6 hours"

## Prerequisites

- ZPA must be active (clusters are only accessible via internal network)
- `curl` and `jq` must be available

## Clusters

| Environment | Endpoint |
|-------------|----------|
| Production | `https://vpc-logs-2020-02-13-2wrvafcked7kjzeqeon55akmhu.us-east-1.es.amazonaws.com` |
| Staging | `https://vpc-logs-stg-2020-02-13-qsmf262aho4qgcfhycdkutjuam.us-east-1.es.amazonaws.com` |
| Club (dedicated) | `https://vpc-es-club-logs-mb2o4255mspnp6abkd7rnw3uxy.us-east-1.es.amazonaws.com` |

No authentication required. If curl times out, the user's ZPA is disconnected.

Kibana UI: append `/_plugin/kibana/app/home` to any endpoint above.

For DataHub domain events (CDC, async integrations), use the skill `kibana-datahub` instead.

## Choosing the Cluster

- **Production** (default): all production application logs
- **Staging**: feature branch and staging environment logs (same field structure, index prefix `stg_` instead of `prd_`)
- **Club dedicated**: Club APIs whose logs live in a separate cluster. If the app starts with `api-club-`, try the Club cluster first; fall back to production if the index doesn't exist.

## Facility and Index Pattern

The **facility** is the most reliable way to identify an application's logs. It is the app name with `-` replaced by `_`:

```
api-product-review       → facility: api_product_review
api-hotpay               → facility: api_hotpay
api-club-content         → facility: api_club_content
```

The index name follows this pattern:

```
prd_log_docker_{facility}_log_{YYYY_MM_DD}   # production
stg_log_docker_{facility}_log_{YYYY_MM_DD}   # staging
```

Always use `*` wildcard for the date portion to search across all available days:
```
prd_log_docker_api_product_review_log_*
```

## Investigation Steps

Follow these steps when the user asks to investigate application logs.

### Step 1: Identify the facility and index

Convert the app name: replace `-` with `_`. Confirm it exists:

```bash
curl -sk 'https://vpc-logs-2020-02-13-2wrvafcked7kjzeqeon55akmhu.us-east-1.es.amazonaws.com/_cat/indices/prd_log_docker_*APPNAME*?h=index&s=index' | tail -5
```

If unsure about the exact name, aggregate active facilities:

```bash
curl -sk "https://vpc-logs-2020-02-13-2wrvafcked7kjzeqeon55akmhu.us-east-1.es.amazonaws.com/prd_log_docker_*_log_*/_search" \
  -H 'Content-Type: application/json' \
  -d '{"size":0,"query":{"range":{"timestamp":{"gte":"now-1h"}}},"aggs":{"f":{"terms":{"field":"facility.keyword","size":50}}}}' \
  | jq '.aggregations.f.buckets[].key' | rg -i "APPNAME"
```

### Step 2: Search for errors

```bash
curl -sk "ENDPOINT/prd_log_docker_FACILITY_log_*/_search" \
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
    "sort": [{"timestamp": {"order": "desc"}}],
    "_source": ["timestamp", "level", "message", "logger", "mdc.traceId", "mdc.uri", "mdc.response-status"]
  }' | jq '.hits.hits[]._source'
```

### Step 3: Trace a request across services

Use the trace ID to find all logs related to a single request, across all apps.
Both `mdc.traceId` and `mdc.trace-id` exist depending on the app, so query both:

```bash
curl -sk "ENDPOINT/prd_log_docker_*_log_*/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "should": [
          {"term": {"mdc.traceId.keyword": "TRACE_ID"}},
          {"term": {"mdc.trace-id.keyword": "TRACE_ID"}}
        ],
        "minimum_should_match": 1
      }
    },
    "size": 50,
    "sort": [{"timestamp": {"order": "asc"}}],
    "_source": ["timestamp", "level", "message", "facility", "mdc.uri", "mdc.response-status", "mdc.time-spent"]
  }' | jq '.hits.hits[]._source'
```

### Step 4: Analyze endpoint latency

```bash
curl -sk "ENDPOINT/prd_log_docker_FACILITY_log_*/_search" \
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
      "status_codes": {"terms": {"field": "mdc.response-status.keyword", "size": 10}},
      "avg_time": {"avg": {"field": "mdc.time-spent"}},
      "p95_time": {"percentiles": {"field": "mdc.time-spent", "percents": [95, 99]}}
    }
  }' | jq '.aggregations'
```

### Step 5: Common filters

Add these to the `must` array as needed:

```json
{"term": {"mdc.acl-sid.keyword": "USER_ID"}}
{"term": {"mdc.client-id.keyword": "CLIENT_ID"}}
{"term": {"log_summary.kubernetes.pod_name.keyword": "POD_NAME"}}
{"term": {"mdc.x-forwarded-for.keyword": "IP"}}
```

To exclude noise, add to `must_not`:
```json
{"match_phrase": {"message": "health-check"}}
```

## Gotchas

- `mdc.time-spent` is a string in some indices and numeric in others. If aggregation fails, try `mdc.timespent` (no hyphen) or treat as keyword.
- Wildcard indices (`prd_*`) work but are slow (30s+). Always restrict to the facility index when possible.
- Logs are retained for ~7 days. Older data is not available.
- The `timestamp` field is ISO 8601 date type. Use `range` with `gte`/`lte` for time filtering.
- For staging, replace `prd_` with `stg_` in the index pattern and use the staging endpoint.

## References

Load these files when additional detail is needed:

- [references/fields.md](references/fields.md) — Read when you need to know all available fields and their types
- [references/club-services.md](references/club-services.md) — Read when investigating a Club app to determine which cluster to query
- [references/advanced-queries.md](references/advanced-queries.md) — Read when you need scroll API, complex aggregations, or field discovery
