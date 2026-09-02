---
inclusion: fileMatch
fileMatchPattern: "**/*.swift"
---

# Swift Conventions — sparkle-ios

General coding rules for all Swift files (SwiftUI, UIKit, domain, networking, etc.).

## Build & Test — Log to File, Grep for Signal

### Build the module after writing code

After writing or modifying code, build the affected **module** to verify it compiles. Building the single module (not the whole app) is fast and catches 99% of issues. Do not build the entire app unless the change spans multiple modules or the user asks for it.

### Simulator (MANDATORY)

Every build AND every test MUST run on this exact simulator — no exceptions:

- **Device:** iPhone 13
- **ID:** `931FBAB2-0456-4D97-9862-C9B31F671028`

Always pass `-destination 'platform=iOS Simulator,id=931FBAB2-0456-4D97-9862-C9B31F671028'`. Do NOT build on "My Mac", a generic destination, or any other simulator. If this specific simulator is not found, ask the user what to do — do NOT silently switch to another simulator.

### Anti-loop failsafe — MAX 3 build attempts

To avoid burning tokens in an infinite build-fix-build-fix loop, cap fix attempts at **3 per task**:

1. Build the module.
2. If it fails, fix the errors and build again.
3. If it fails a second time, fix and build a third time.
4. If it STILL fails after the 3rd attempt: **STOP building.** Do not try again. Summarize the remaining errors, explain the likely root cause, and hand it back to the user. Building a 4th time on your own is forbidden.

If two consecutive attempts hit the same error, that also counts as a signal to stop and reconsider the root cause rather than patching blindly.

### When to use tuist (and when NOT to)

Modules are Swift Packages (they have a `Package.swift`). To build or test a single module you MUST use `xcodebuild -scheme` directly against the package. Do NOT run `tuist generate`, `tuist build`, or any tuist command to verify a module you just edited — it is unnecessary and slow.

`tuist` is ONLY for:

- Running a module's **Example** app (the `Example/` folder inside a module)
- Generating/building the **main app** workspace

For everything else — verifying that an edited module compiles or running its tests — build the module directly with `xcodebuild -scheme`, never tuist.

### How to build — log to file, never stream

NEVER stream the full build output into context. `xcodebuild` produces thousands of lines that would bloat the context and risk compaction. Always redirect to a log file and extract only what you need with ripgrep (`rg`).

**Step 1 — build the module, redirect output, capture only the exit code:**

```bash
cd ios/Features/<ModuleName>/<ModuleName>/ && \
xcodebuild build \
  -scheme "<ModuleName>" \
  -destination 'platform=iOS Simulator,id=931FBAB2-0456-4D97-9862-C9B31F671028' \
  -skipPackagePluginValidation \
  -IDEBuildingContinueBuildingAfterErrors=YES \
  > /tmp/sparkle-build.log 2>&1; echo "exit: $?"
```

`-IDEBuildingContinueBuildingAfterErrors=YES` makes the build keep going past the first error so a single run surfaces ALL compile errors at once, instead of stopping at the first file that fails. This saves fix-build cycles — fix everything the log reports, then rebuild once.

Only `exit: <code>` enters context. The full log stays on disk. (Use `xcodebuild test` instead of `build` when the user asks to run tests — see the `sparkle-tests` skill.)

**Step 2 — extract only the signal you need:**

```bash
# Compilation errors
rg "error:" /tmp/sparkle-build.log

# Final result
rg "BUILD FAILED|BUILD SUCCEEDED" /tmp/sparkle-build.log
```

**Step 3 — if you need more detail on a specific error, search with surrounding context (never cat the whole file):**

```bash
rg -A 5 -B 2 "error:" /tmp/sparkle-build.log
```

## Constants — No Magic Numbers

All constants/magic numbers (CGFloat, Int, TimeInterval, etc.) MUST be declared in a `private enum Constants` inside the struct/class where they are used.

```swift
struct MyView: View {
    private enum Constants {
        static let chartHeight: CGFloat = 144
        static let iconSize: CGFloat = 48
        static let animationDuration: TimeInterval = 0.3
        static let maxRetries: Int = 3
    }
}
```

For generic types (where Swift disallows static stored properties), use a file-level private enum:

```swift
private enum MyViewConstants {
    static let chipHeight: CGFloat = 28
}

struct MyView<Content: View>: View { ... }
```

## Strings — Localization Rules

User-facing text (labels, titles, messages, button text, placeholders, accessibility labels) MUST be defined in the module's `Localizable.strings` (pt-BR) and accessed via the generated `Strings` enum (SwiftGen). NEVER hardcode a string that the user will see.

```swift
// FORBIDDEN
Text("Nenhuma venda encontrada")
.navigationTitle("Extrato")
label.text = "Carregando..."

// CORRECT — use generated Strings
Text(Strings.Sales.emptyState)
.navigationTitle(Strings.Statement.title)
label.text = Strings.Common.loading
```

### What does NOT go in Localizable

These strings stay hardcoded or in constants — they are not user-facing:

- API paths and URLs (e.g. `"/v2/wallet/sales"`)
- Analytics event names and keys (e.g. `"wallet_dashboard_viewed"`)
- Log messages (e.g. `"Failed to decode response"`)
- Internal identifiers and keys (e.g. `"featureFlag.walletV2"`)
- JSON/Codable keys
- Notification names
- UserDefaults keys
