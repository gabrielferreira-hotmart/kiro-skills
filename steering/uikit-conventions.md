---
inclusion: fileMatch
fileMatchPattern: "**/*.swift"
---

# UIKit Conventions

## AutoLayout Constraints

When building views using UIKit, you MUST prefer using the helper methods defined in `ios/Core/uUI/uUI/Sources/Extensions/UIView+Autolayout.swift`.

### Available methods

- `anchor(top:leading:bottom:trailing:topConstant:leadingConstant:bottomConstant:trailingConstant:widthConstant:heightConstant:)` — pin edges with constants
- `anchor(top:left:bottom:right:topConstant:leftConstant:bottomConstant:rightConstant:widthConstant:heightConstant:)` — pin edges (left/right variant)
- `fillSuperview(topConstant:leadingConstant:bottomConstant:trailingConstant:)` — pin all edges to superview
- `anchorCenterXToSuperview(constant:)` — center horizontally in superview
- `anchorCenterYToSuperview(constant:)` — center vertically in superview

### When to use raw NSLayoutConstraint instead

Only write constraints manually (via `NSLayoutConstraint` or anchor API directly) when:

- You need `greaterThanOrEqualTo` or `lessThanOrEqualTo` relationships
- You need to keep a reference to a constraint to activate/deactivate/update it later
- You need multiplier-based constraints
- The helpers above genuinely don't cover your use case

### Examples

```swift
// GOOD — use fillSuperview
view.addSubview(childView)
childView.fillSuperview()

// GOOD — use anchor with specific edges
view.addSubview(childView)
childView.anchor(
    top: view.topAnchor,
    leading: view.leadingAnchor,
    trailing: view.trailingAnchor,
    topConstant: 16,
    leadingConstant: 16,
    trailingConstant: 16,
    heightConstant: 44
)

// BAD — manual constraints when fillSuperview would work
view.addSubview(childView)
childView.translatesAutoresizingMaskIntoConstraints = false
NSLayoutConstraint.activate([
    childView.topAnchor.constraint(equalTo: view.topAnchor),
    childView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
    childView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
    childView.bottomAnchor.constraint(equalTo: view.bottomAnchor)
])
```
