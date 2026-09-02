---
inclusion: fileMatch
fileMatchPattern: "**/*.swift"
---

# Code Comments Policy

## Rules

- Do NOT add obvious or verbose comments to the code.
- Only add comments when:
  - The logic is genuinely hard to understand
  - There's a non-obvious decision or workaround (a.k.a. gambiarra)
  - There's a "why" that isn't clear from the code itself
- The code should be self-documenting. Good naming and structure replace the need for comments.
- Never comment what the code already says (e.g. `// returns the user` above a `return user` line).
- Prefer zero comments over redundant comments.
