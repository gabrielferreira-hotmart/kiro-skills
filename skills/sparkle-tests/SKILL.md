---
name: "sparkle-tests"
description: "Roda testes unitários do sparkle-ios via SPM. Equivale a abrir o módulo no Xcode e pressionar Cmd+U."
keywords: ["tests", "sparkle", "xcodebuild", "spm", "unit-tests", "module-tests", "swift-package", "snapshot"]
---

# Sparkle iOS — Testing

## Estrutura dos módulos

```
ios/
├── Features/<ModuleName>/<ModuleName>/Package.swift
└── Core/<ModuleName>/<ModuleName>/Package.swift
```

## Como rodar testes de um módulo

ALWAYS redirect output to a log file and search it with ripgrep (`rg`) — never stream the full xcodebuild output into context (thousands of lines bloat context and risk compaction).

```bash
cd ios/Features/<ModuleName>/<ModuleName>/ && \
xcodebuild test \
  -scheme "<ModuleName>" \
  -destination 'platform=iOS Simulator,id=931FBAB2-0456-4D97-9862-C9B31F671028' \
  -skipPackagePluginValidation \
  -IDEBuildingContinueBuildingAfterErrors=YES \
  -testLanguage pt \
  -testRegion BR \
  > /tmp/sparkle-tests.log 2>&1; echo "exit: $?"
```

Only `exit: <code>` enters context. Then extract signal:

```bash
rg "error:" /tmp/sparkle-tests.log                                   # compile errors
rg "Test Case.*failed|failed \(.*seconds\)" /tmp/sparkle-tests.log   # failed tests
rg "TEST SUCCEEDED|TEST FAILED|BUILD FAILED" /tmp/sparkle-tests.log   # final result
rg -A 5 -B 2 "error:" /tmp/sparkle-tests.log                         # detail on an error
```

### Simulador (obrigatório)

- **Device:** iPhone 13
- **ID:** `931FBAB2-0456-4D97-9862-C9B31F671028`

Se o simulador não for encontrado, perguntar ao usuário antes de prosseguir.

### Rodar teste específico

```bash
# Classe de teste
-only-testing:<ModuleName>Tests/<TestClassName>

# Método de teste
-only-testing:<ModuleName>Tests/<TestClassName>/<testMethodName>
```

Múltiplos `-only-testing` podem ser combinados no mesmo comando.

### Pular LocalizableTests

```bash
-skip-testing:<ModuleName>Tests/LocalizableTests
```

LocalizableTests valida paridade pt-BR/en/es — como só pt-BR é mantido por devs, ele falha. Ignorar ou pular.

### Flag obrigatória

`-skipPackagePluginValidation` — sem ela o build falha por validação de plugins SPM.

### Interpretar resultados

Sempre lendo do log em `/tmp/sparkle-tests.log`:

- `** TEST SUCCEEDED **` → tudo ok
- `** TEST FAILED **` → verificar quais falharam
- `** BUILD FAILED **` → erro de compilação

## Módulos pesados — uWallet

~3000 testes, ~8 minutos. Estratégia:

1. Rode a suite completa apenas UMA vez para identificar falhas
2. Após identificar, rode apenas os testes específicos que falharam
3. Snapshot tests precisam de 2 runs (primeira grava, segunda valida)

---

## Test Conventions

### Estrutura de arquivos

```
Tests/<ModuleName>Tests/
├── Helpers/
│   └── TestDoubles.swift
├── Scenes/
│   └── SceneName/
│       ├── InteractorTests.swift
│       ├── PresenterTests.swift
│       └── ViewControllerTests.swift
```

### Test Doubles

**Spies** (verificam comportamento):
- Nomeados `<Protocol>Spy`
- `private(set) var didCall<Method> = false`
- `private(set) var <param>Passed: Type?`
- `var <result>ToReturn: Type` para stubbing
- `var on<Method>: (() -> Void)?` para coordenação async

```swift
final class PresenterSpy: PresentationLogic {
    var didCallPresentProduct = false
    var presentProductResponsePassed: ProductResponse?

    func presentProduct(response: ProductResponse) {
        didCallPresentProduct = true
        presentProductResponsePassed = response
    }
}
```

**Stubs**: `<Protocol>Stub` ou `<Protocol>SuccessStub` / `<Protocol>ErrorStub`
**Dummies**: `<Protocol>Dummy` — satisfazem protocolo sem comportamento

### Unit Test Pattern — Given/When/Then com `makeSUT`

```swift
final class PresenterTests: XCTestCase {
    func test_presentProduct_shouldCallDisplayContent() {
        // Given
        let viewControllerSpy = DisplayLogicSpy()
        let sut = makeSUT(displayLogic: viewControllerSpy)

        // When
        sut.presentProduct(response: .mock)

        // Then
        XCTAssertTrue(viewControllerSpy.didCallDisplayContent)
    }

    private func makeSUT(displayLogic: DisplayLogic) -> Presenter {
        let sut = Presenter()
        sut.viewController = displayLogic
        return sut
    }
}
```

### Async tests

```swift
func test_onViewDidLoad_shouldCallUseCase() {
    let expectation = XCTestExpectation(description: "Wait for useCase")
    useCaseSpy.onExecute = { expectation.fulfill() }

    sut.onViewDidLoad()

    wait(for: [expectation], timeout: 1)
    XCTAssertTrue(useCaseSpy.executeCalled)
}
```

### Mock Data Pattern

```swift
extension ProductResponse {
    static let mock = ProductResponse(
        name: "Test Product",
        description: "Test description"
    )
}
```

---

## Snapshot Tests

- Import `SnapshotTesting`, `uXCTest`, `HotmartCosmos`
- Em `setUp()`: registrar `CosmosImageFetcherDummy()` e setar `CommonL10n.language = "pt-BR"`
- Usar `assertLightAndDarkSnapshot` para UIViewController (testa light + dark em iPhoneXr e iPadPro11)

```swift
func test_displayContent_shouldShowProductInfo() {
    assertLightAndDarkSnapshot {
        let sut = makeSUT()
        sut.loadView()
        sut.displayContent(viewModel: .mock)
        return sut
    }
}
```

### First run behavior

1. Testes falham na primeira execução: "No reference was found on disk. Automatically recorded snapshot..."
2. Gravam reference images em `__Snapshots__/` ao lado do arquivo de teste
3. Na segunda execução, passam comparando contra a referência

**Snapshot tests são esperados falhar na primeira execução.** Rode duas vezes.

### Quando snapshots ficam desatualizados

1. Delete as imagens na pasta `__Snapshots__/` relevante
2. Rode testes — falham e gravam novas referências
3. Rode novamente — passam

### Para gravar/regravar

Set env var `RECORD_SNAPSHOTS=TRUE` ou passe `record: true` na assertion.

---

## Imports Pattern

```swift
import Foundation
import HotmartCosmos
import SnapshotTesting
@testable import uFeatureModule
import uXCTest
import XCTest
```

## Dependências de teste

- `uXCTest`: `assertLightAndDarkSnapshot`, `UINavigationControllerSpy`, `UIViewControllerSpy`
- `SnapshotTesting`: swift-snapshot-testing (PointFree)
- `uSharedDependencyCosmos`: brand libraries para snapshot (light/dark)
