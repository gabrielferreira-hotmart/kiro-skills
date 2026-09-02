---
inclusion: always
---

# Sub-Agent Usage Policy

Always prefer delegating work to sub-agents when the task benefits from it.

## Rules

- Use `context-gatherer` before making changes in unfamiliar areas of the codebase, investigating bugs, or when the relevant files are not immediately clear.
- Use `general-task-execution` to parallelize independent subtasks or delegate well-defined units of work.
- Use `semantic_reviewer` only for multi-file, architectural, behavior-changing, or security-sensitive changes **when no build or test was run during the current execution**.
- If a build or test already ran during the current execution, do NOT invoke `semantic_reviewer`; the build/test validation takes precedence and avoids redundant review overhead.
- Prefer sub-agents over doing all the work sequentially in the main context, especially for:
  - Exploring the codebase to find relevant files
  - Investigating how components interact
  - Understanding patterns and conventions used in the project
  - Reviewing changes for correctness and design quality

## Mandatory Silent Mode for Sub-Agents

**CRITICAL: Every sub-agent invocation MUST use the `silentmode` skill. This is mandatory and must never be skipped.**

Before delegating work, instruct the sub-agent to activate/use `silentmode` so it does not waste context on tool-call narration. The sub-agent should return only its concise final result, findings, or requested output. This rule applies to `context-gatherer`, `general-task-execution`, `semantic_reviewer`, and any other sub-agent.

## Cost-Aware Usage

Sub-agents reduce pressure on the main context window, especially with large investigations and models with smaller context windows. They also have per-call overhead because each sub-agent may load its applicable steering and context. Use them selectively:

- Use `context-gatherer` for unfamiliar code areas, complex bugs, or broad dependency tracing.
- Use `general-task-execution` only for genuinely independent subtasks or well-defined delegated work.
- Do not use a sub-agent for a simple edit when the exact file and change are already known.
- Use `semantic_reviewer` only for multi-file, architectural, behavior-changing, or security-sensitive changes.
- Do not parallelize by default; every additional sub-agent adds cost.

Prefer the smallest number of focused sub-agents that keeps the main context manageable.
