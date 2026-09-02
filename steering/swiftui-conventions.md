---
inclusion: fileMatch
fileMatchPattern: "**/*.swift"
---

# SwiftUI Conventions — sparkle-ios

When writing SwiftUI views in this project, follow these conventions.

## CRITICAL RULES

### Never use HotmartCosmos in SwiftUI

In SwiftUI code you MUST use **CosmosGlobal** exclusively. The `HotmartCosmos` package is UIKit-only and MUST NOT be imported or used in any SwiftUI view, view model, or SwiftUI-related file.

```swift
// FORBIDDEN in SwiftUI files
import HotmartCosmos
Cosmos.setBrandLibrary(...)

// CORRECT — always use CosmosGlobal
import uSharedDependencyCosmosGlobal
CosmosGlobal.Colors.Semantic.Interface.foreground.color
CosmosGlobal.Spacing.spacing4
```

Note: `HotmartCosmos` is only used in UIKit production code and in XCTest snapshot test files (for brand library setup). It has no place in SwiftUI code.

---

## Design Tokens — CosmosGlobal Only

All visual values MUST come from CosmosGlobal tokens. Never hardcode colors, spacing, border radius, or typography.

### FORBIDDEN — Never do this

```swift
// NEVER hardcode fonts
.font(.custom("HotmartSans-Bold", size: 14))
.font(.system(size: 16, weight: .bold))

// NEVER hardcode colors
.foregroundColor(.white)
.foregroundColor(Color(red: 0.13, green: 0.54, blue: 0.33))
.background(Color(hex: "#F5F3EF"))

// ALWAYS use tokens instead
.cosmosTypography(TailwindTextSizes.textSm)
.foregroundColor(CosmosGlobal.Colors.Semantic.Interface.foreground.color)
.background(CosmosGlobal.Colors.Semantic.Interface.offBackground.color)
```

Fonts MUST always use `.cosmosTypography()` — this ensures the correct font family, weight, size, and line height are applied together. Hardcoding `.font(.custom(...))` or `.font(.system(...))` breaks design consistency and will not adapt to typography token updates.

Colors MUST always use semantic tokens from CosmosGlobal — they automatically adapt to dark/light mode. Using raw SwiftUI colors (`.white`, `.black`, `Color(hex:)`) will break in dark mode.

### Acceptable exceptions

- `.tint()` can receive a CosmosGlobal token to override system accent color on native components (DatePicker, Toggle, etc.).

### Colors

Use `CosmosGlobal.Colors.Semantic.Interface.*`:

| Token | Usage |
|-------|-------|
| `.foreground` | Primary text, primary dark fills (#0D0D0D) |
| `.mutedForeground` | Secondary/subtitle text (#7A7773) |
| `.secondaryForeground` | Disabled/placeholder icons |
| `.secondary` | Inverse text (white on dark backgrounds) |
| `.background` | Page background (white) |
| `.offBackground` | Light grey card background (#F5F3EF) |
| `.muted` | Skeleton/loading fills |
| `.border` | Standard border (#DCDAD6) |
| `.borderLight` | Subtle border (#EAE9E7) |
| `.positive` | Green accent (#0BD043) |
| `.positiveLight` | Light green (#B7F6CB) |
| `.primary` | Primary action color |
| `.card` | Card background (white) |

Never use `FakeCosmosGlobal` — it's legacy UIKit only.

### Typography

Use `.cosmosTypography()` modifier with these tokens:

| Token | Usage |
|-------|-------|
| `ProductTextSizes.titleMdHeaderSerif` | Large serif headings (24px, Hotmart Display) |
| `ProductTextSizes.titleMdSubheading` | Subtitle under headings (16px, Hotmart Sans) |
| `ProductTextSizes.titleSmHeader` | Section headers (20px) |
| `ProductTextSizes.titleXsHeaderSerif` | Card values (16px, Hotmart Display) |
| `ProductTextSizes.titleXsOverline` | Uppercase overline labels (10px, 0.2em letter-spacing) |
| `TailwindTextSizes.textBase` | Body text (16px) |
| `TailwindTextSizes.textSm` | Small body text (14px) |
| `TailwindTextSizes.textXs` | Extra small text (12px) |

### Spacing

Use `CosmosGlobal.Spacing.*`:

- `spacing1` (4px), `spacing1_5` (6px), `spacing2` (8px), `spacing3` (12px), `spacing4` (16px), `spacing6` (24px)

### Border Radius

Use `CosmosGlobal.BorderRadius.*`:

- `.sm`, `.md`, `.lg` (12px), `.xl` (16px)

### Border Width

Use `CosmosGlobal.BorderWidth.borderWidth1` for 1px borders.

## Icons

Prefer `CosmosGlobal.Icons.*` over SF Symbols when a matching icon exists:

```swift
// Available icons: CosmosGlobal.Icons.Reserved.* and CosmosGlobal.Icons.Others.*
CosmosGlobal.Icons.Reserved.calendar.image(size: .sm)    // 14pt
CosmosGlobal.Icons.Reserved.chevronRight.image(size: .md) // 16pt
CosmosGlobal.Icons.Others.receipt.image(size: .lg)       // 18pt
```

Icon sizes: `.xs` (12), `.sm` (14), `.md` (16), `.lg` (18), `.xl` (20), `.xl2` (24)

Use SF Symbols (`Image(systemName:)`) only when no CosmosGlobal equivalent exists (e.g. `chevron.down`). When using SF Symbols, size them with `.resizable()` + `.frame()` — never use `.font(.system(size:))`:

```swift
// CORRECT
Image(systemName: "chevron.down")
    .resizable()
    .scaledToFit()
    .frame(width: Constants.chevronSize, height: Constants.chevronSize)
    .foregroundColor(CosmosGlobal.Colors.Semantic.Interface.foreground.color)

// FORBIDDEN
Image(systemName: "chevron.down")
    .font(.system(size: 10, weight: .medium))
```

## CosmosButton

Use `CosmosButton` for all buttons that follow the design system. Available modifiers:

```swift
CosmosButton("Label") { action() }
    .variant(.primary)       // .primary | .outline | .ghost
    .size(.sm)               // .sm | .default
    .isPill()                // capsule shape (border-radius: full)
    .icon(.prefix(iconToken)) // leading icon from CosmosGlobal.Icons.*
    .isFullWidth(true)       // stretches to fill width
    .disabled(condition)
```

For a button that is only an icon (no label): `CosmosButton(action: { ... })` without a title string.

## Bottom Sheets & Modals

Prefer the native SwiftUI `.sheet` over `CosmosBottomSheet` when:
- You don't need the dark overlay/dimming
- You need standard iOS drag-to-dismiss behavior
- The content is a form or picker (DatePicker, calendar, etc.)

```swift
.sheet(isPresented: $showSheet) {
    VStack(spacing: 0) {
        // content
        Spacer()
        // footer buttons
    }
    .padding(.horizontal, CosmosGlobal.Spacing.spacing4)
    .presentationDetents([.medium])  // or [.medium, .large]
    .presentationDragIndicator(.visible)
    .tint(CosmosGlobal.Colors.Semantic.Interface.foreground.color)
}
```

Use `CosmosBottomSheet` when you need:
- The drag handle + close/back button header pattern
- Title + description header (`CosmosBottomSheetHeader`)
- Controlled detent height based on content

Note: `CosmosBottomSheet` always renders a dark overlay (opacity 0.8) with no option to disable it.

## View State Pattern

Use a dedicated enum for view states:

```swift
enum MyFeatureViewState {
    case idle
    case loading
    case empty
    case error
    case loaded
}
```

Switch on it in the view body:

```swift
var body: some View {
    Group {
        switch viewModel.viewState {
        case .idle: Color.clear
        case .loading: loadingView
        case .empty: EmptyStateView()
        case .error: ErrorStateView(onRetry: { viewModel.retry() })
        case .loaded: loadedView
        }
    }
    .onAppear { viewModel.loadIfNeeded() }
}
```

## ViewModel Pattern

- Use `ObservableObject` with `@Published private(set)` for state
- Expose `loadIfNeeded()`, `retry()`, `refresh()` as public methods
- Cache `NumberFormatter` and `DateFormatter` as `private static let`
- Wrap async callbacks in `DispatchQueue.main.async` for thread safety

## Localization

- All user-facing strings go in `pt-BR.lproj/Localizable.strings`
- Use SwiftGen-generated `L10n.*` accessors
- Never hardcode text in views — even short labels like "7d" must be localized
- After modifying strings, run: `cd ios/Features/<module> && swiftgen config run --config swiftgen.yml`

## File Structure

Organize features in subfolders:

```
Feature/
├── FeatureView.swift
├── FeatureViewModel.swift
├── Chart/
│   ├── ChartView.swift
│   └── ChartModels.swift
├── Filters/
│   ├── FilterView.swift
│   └── FilterModels.swift
├── States/
│   ├── EmptyStateView.swift
│   └── ErrorStateView.swift
├── Summary/
│   └── SummaryCardsView.swift
└── UseCase/
    ├── UseCaseProvider.swift
    ├── UseCaseModels.swift
    └── MockUseCase.swift
```

## Card Styling Pattern

```swift
VStack(alignment: .leading, spacing: CosmosGlobal.Spacing.spacing3) {
    Text(title)
        .cosmosTypography(ProductTextSizes.titleXsOverline)
        .foregroundColor(CosmosGlobal.Colors.Semantic.Interface.mutedForeground.color)
    Text(value)
        .cosmosTypography(ProductTextSizes.titleXsHeaderSerif)
        .foregroundColor(CosmosGlobal.Colors.Semantic.Interface.foreground.color)
}
.frame(maxWidth: .infinity, alignment: .leading)
.padding(CosmosGlobal.Spacing.spacing4)
.background(CosmosGlobal.Colors.Semantic.Interface.offBackground.color)
.clipShape(RoundedRectangle(cornerRadius: CosmosGlobal.BorderRadius.lg))
.overlay(
    RoundedRectangle(cornerRadius: CosmosGlobal.BorderRadius.lg)
        .stroke(
            CosmosGlobal.Colors.Semantic.Interface.borderLight.color,
            lineWidth: CosmosGlobal.BorderWidth.borderWidth1
        )
)
```

## Chip/Pill Styling Pattern

Outline chip (e.g. currency selector):
```swift
HStack(spacing: CosmosGlobal.Spacing.spacing1) {
    icon
    Text(label).cosmosTypography(TailwindTextSizes.textSm)
    Image(systemName: "chevron.down")
}
.padding(.horizontal, CosmosGlobal.Spacing.spacing2)
.padding(.vertical, CosmosGlobal.Spacing.spacing2)
.background(CosmosGlobal.Colors.Semantic.Interface.card.color)
.clipShape(Capsule())
.overlay(Capsule().stroke(CosmosGlobal.Colors.Semantic.Interface.border.color, lineWidth: CosmosGlobal.BorderWidth.borderWidth1))
```

Filled chip (e.g. active filter):
```swift
HStack(spacing: CosmosGlobal.Spacing.spacing1) {
    icon.foregroundColor(CosmosGlobal.Colors.Semantic.Interface.secondary.color)
    Text(label).cosmosTypography(TailwindTextSizes.textSm)
        .foregroundColor(CosmosGlobal.Colors.Semantic.Interface.secondary.color)
}
.padding(.horizontal, CosmosGlobal.Spacing.spacing2)
.padding(.vertical, CosmosGlobal.Spacing.spacing2)
.background(CosmosGlobal.Colors.Semantic.Interface.foreground.color)
.clipShape(Capsule())
```

## Error State Pattern

```swift
struct ErrorStateView: View {
    let onRetry: () -> Void

    var body: some View {
        VStack(spacing: CosmosGlobal.Spacing.spacing3) {
            Spacer()
            Image(systemName: "exclamationmark.triangle")
                .resizable()
                .scaledToFit()
                .frame(width: Constants.iconSize, height: Constants.iconSize)
                .foregroundColor(CosmosGlobal.Colors.Semantic.Interface.secondaryForeground.color)
            Text(L10n.errorTitle)
                .cosmosTypography(ProductTextSizes.titleSmHeader)
                .foregroundColor(CosmosGlobal.Colors.Semantic.Interface.foreground.color)
            Text(L10n.errorSubtitle)
                .cosmosTypography(TailwindTextSizes.textSm)
                .foregroundColor(CosmosGlobal.Colors.Semantic.Interface.mutedForeground.color)
            Button(action: onRetry) {
                Text(L10n.retryButton)
                    .cosmosTypography(TailwindTextSizes.textSm)
                    .foregroundColor(CosmosGlobal.Colors.Semantic.Interface.background.color)
                    .padding(.horizontal, CosmosGlobal.Spacing.spacing4)
                    .padding(.vertical, CosmosGlobal.Spacing.spacing3)
                    .background(CosmosGlobal.Colors.Semantic.Interface.foreground.color)
                    .clipShape(RoundedRectangle(cornerRadius: CosmosGlobal.BorderRadius.md))
            }
            Spacer()
        }
        .padding(CosmosGlobal.Spacing.spacing4)
    }
}
```
