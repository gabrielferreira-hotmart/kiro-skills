---
inclusion: always
---

# MCP Tooling Rules

## Mandatory compressed MCPs

For Git, GitHub, and Atlassian operations, ALWAYS use the configured compressed MCP servers first:

- Git operations → `mcp_git_compressed_server`
- GitHub operations → `mcp_github_compressed_server`
- Jira/Confluence operations → `mcp_atlassian_compressed_server`

Do NOT use `gh`, raw GitHub API calls, direct HTTP requests, or other CLI alternatives for these operations when the corresponding compressed MCP is available. This includes repository access, repository metadata, branches, commits, pull requests, issues, Git status, Jira issues, and Confluence pages.

Use the compressed MCP tool's schema lookup before invoking an unfamiliar tool. If a compressed MCP call fails or is unavailable, report the failure instead of silently falling back to `gh` or another equivalent. A fallback requires explicit user authorization, except when the user explicitly asks for the CLI.
