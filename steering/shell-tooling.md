---
inclusion: always
---

# Shell Tooling Preferences

Prefer modern, faster tools when running terminal commands.

## Use ripgrep (`rg`) instead of grep

`rg` is installed and is faster than `grep`. Use it for all text searches in the terminal.

| Instead of | Use |
|------------|-----|
| `grep "pat" file` | `rg "pat" file` |
| `grep -E "a|b" file` | `rg "a|b" file` (rg is regex by default, no `-E` needed) |
| `grep -r "pat" dir/` | `rg "pat" dir/` (recursive by default) |
| `grep -i "pat"` | `rg -i "pat"` |
| `grep -A 5 -B 2 "pat"` | `rg -A 5 -B 2 "pat"` (context flags are identical) |
| `grep -l "pat"` | `rg -l "pat"` |
| `grep -c "pat"` | `rg -c "pat"` |

### Notes

- `rg` treats the pattern as a regex by default — drop `-E`.
- `rg` searches recursively and skips `.gitignore`d files by default. Use `-uu` to include ignored/hidden files.
- Fixed-string search: `rg -F "literal"`.
- For dedicated file/content search during a task, prefer the built-in search tools over shelling out. Use `rg` in the terminal when a tool isn't a good fit (e.g. searching a log file in `/tmp`).
