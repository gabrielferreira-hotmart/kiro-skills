---
inclusion: always
---

# Git Safety — No Auto Commit/PR

## Rules

- NEVER run `git commit` unless the user explicitly asks to commit.
- NEVER create a Pull Request unless the user explicitly asks to open a PR.
- NEVER stage or commit any `Specs/` directory or files inside it, even when the user explicitly asks to commit. Exclude every path component named `Specs` (case-sensitive) from commit operations.
- The user handles commits and PRs manually.
