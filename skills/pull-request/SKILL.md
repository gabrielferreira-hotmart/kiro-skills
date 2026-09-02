---
name: "pull-request"
description: "Regras para criar PRs no sparkle-ios: título, body template, base branch, e formatação."
keywords: ["pr", "pull-request", "github", "review", "merge"]
---

# Pull Requests — sparkle-ios

## Language

- PR titles and descriptions MUST be written in **English**.
- Commit messages should also be in English.

## Título do PR

Formato:

```
[TASK-ID] Short description of what was done
```

### Flags no título

| Flag | Quando usar |
|------|-------------|
| `[NOCHANGE]` | PR **não altera o CHANGELOG**. Mudança interna (feature flags, refactors, configs) sem impacto ao usuário final. |

### Exemplos

```
[MCG-2024][NOCHANGE] Add feature flag and fix SCK for explore recommendation
[MCG-2195] Add recommendation on explore screen
[CAA-5190][NOCHANGE] Refactor analytics tracking
```

### Quando usar [NOCHANGE]

- Feature flags que ainda não estão ativas
- Refactors internos sem mudança de comportamento visível
- Correções de código que não alteram funcionalidade do usuário
- Ajustes de configuração/infra

### Quando NÃO usar [NOCHANGE]

- Novas features visíveis ao usuário
- Correções de bugs reportados
- Mudanças de UI/UX
- Qualquer coisa que mereça uma entrada no CHANGELOG

## Base branch

- PRs de subtasks vão para a **feature branch pai** (ex: `MCG-2215` → `feature/MCG-2195`)
- PRs de tasks independentes ou feature branches vão para **develop**

## PR Body Template

O body DEVE seguir o template do projeto (`.github/pull_request_template.md`):

```markdown
## What was done?

<!-- List the main changes made -->

## Why was it done?

<!-- Explain the reason behind the change -->

## Added any feature toggle?

- [ ] Yes
- [x] No

## Evidence

<!-- Screenshots for visual changes, or description of testing for non-visual changes -->

## If something goes wrong with these changes, we must:

- [ ] Revert this PR
- [ ] Disable the feature toggle
- [ ] Run to the hills
- [ ] Other (please specify)

## Reference Links

- [TASK-ID] Task description

[TASK-ID]: https://hotmart.atlassian.net/browse/TASK-ID
```

### Rules

- Always include ALL sections from the template — do not invent custom sections
- The "Reference Links" section should be kept exactly as the default template. Do NOT replace or customize it with Jira links.
- Mark the appropriate checkboxes for feature toggle and rollback plan
- If there's no visual change, say so explicitly in Evidence (e.g. "No visual changes — data-fetching behavior only. Unit tests passing.")
- Do NOT add `[TRIVIAL]` flag unless the user explicitly requests it

## GitHub API Formatting

When creating PRs via the GitHub API (`create_pull_request` or `edit_pull_request`), NEVER use literal `\n` in the body string. The API expects actual newlines in the JSON string value. Write the body as a normal multi-line markdown string — the tool handles JSON serialization.
