# Available Fields

## Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `level` | keyword | Log level: `INFO`, `ERROR`, `WARN`, `DEBUG` |
| `message` | text | Log message body (supports full-text search) |
| `logger` / `loggerName` | text | Java class that produced the log |
| `facility` | keyword | Internal application name (underscore format) |
| `timestamp` | date | ISO 8601 timestamp |
| `thread` | keyword | Execution thread |
| `context` | keyword | Application context |
| `exception` | text | Full stack trace (when present) |

## MDC Fields (Mapped Diagnostic Context)

Present in most applications:

| Field | Type | Description |
|-------|------|-------------|
| `mdc.traceId` | keyword | Distributed trace ID |
| `mdc.trace-id` | keyword | Trace ID variant (legacy apps) |
| `mdc.spanId` | keyword | Span ID |
| `mdc.parentId` | keyword | Parent span ID |
| `mdc.uri` | text + keyword | Request URI |
| `mdc.method` | keyword | HTTP method |
| `mdc.response-status` | keyword | HTTP status code |
| `mdc.time-spent` | keyword/long | Response time in ms (type varies by app) |
| `mdc.timespent` | keyword/long | Variant without hyphen |
| `mdc.acl-sid` | keyword | Authenticated user ID |
| `mdc.user` | keyword | User ID variant |
| `mdc.client-id` | keyword | OAuth2 client ID |
| `mdc.remote-address` | keyword | Server/pod IP |
| `mdc.x-forwarded-for` | keyword | Real client IP |
| `mdc.user-agent` | text + keyword | User-Agent header |
| `mdc.local-hostname` | keyword | Pod hostname |

## Kubernetes Fields

| Field | Description |
|-------|-------------|
| `log_summary.kubernetes.pod_name` | Pod name |
| `log_summary.kubernetes.namespace_name` | K8s namespace |
| `log_summary.kubernetes.host` | EC2 host |
| `log_summary.kubernetes.pod_ip` | Pod IP |
| `log_summary.kubernetes.container_name` | Container name |
| `log_summary.kubernetes.container_image` | Full Docker image |

## Query Tips

- `text` fields support `match` (partial) and `match_phrase` (exact phrase)
- `keyword` fields use `term` for exact match or `wildcard` for patterns
- For fields with both text + keyword, use `mdc.uri` for partial search and `mdc.uri.keyword` for exact match
- Use `_source` in the request to limit returned fields (saves bandwidth and improves readability)
- Each app may have additional MDC fields specific to its domain. Use field discovery to explore.
