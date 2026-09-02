---
inclusion: fileMatch
fileMatchPattern: '**/Localizable.strings'
---

# Localization Rules

## Only modify pt-BR

When adding or modifying localized strings (Localizable.strings), **only modify the `pt-BR.lproj/Localizable.strings` file**.

Do NOT add or modify strings in:
- `en.lproj/Localizable.strings`
- `es.lproj/Localizable.strings`
- Any other language files

The other languages are handled by an external translation service. Only pt-BR is the source of truth maintained by developers.

## SwiftGen

After modifying `pt-BR.lproj/Localizable.strings`, run SwiftGen to regenerate the `Strings.swift` file:

```bash
cd ios/Features/<module> && swiftgen config run --config swiftgen.yml
```
