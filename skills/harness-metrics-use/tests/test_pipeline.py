#!/usr/bin/env python3
"""test_pipeline.py — testes mínimos com fixture sintético + golden asserts.

Sem framework externo (só stdlib). Roda o pipeline inteiro sobre um intermediate
sintético e valida os invariantes que o review do PR #25 apontou como frágeis:

  - classificação de actionType resiliente a camelCase E snake_case (bloqueador 1);
  - fallback por verbo cobre MCP/ferramentas novas; canário só pega o irreconhecível;
  - créditos (promptTurnSummaries) e elapsedTime lidos (bloqueador 2);
  - 1ª tarefa da sessão NÃO é confidence:low (bug de segmentação);
  - hallucination reportada como TAXA por tarefa;
  - sinais determinísticos: tool_rejection_rate (via selectedOption, formato 1.0.395),
    aborted_turn_rate e context_truncation (tombstone).

Uso:
    python3 tests/test_pipeline.py
Sai com código 0 se tudo passar; imprime o primeiro erro e sai !=0 caso contrário.
"""
from __future__ import annotations

import sys
from pathlib import Path

# permite importar os scripts irmãos
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import actions
import segment as seg
import metrics_deterministic as md
import metrics_trend as mt


def _tool_call(action, file_path=None, command=None):
    payload = {"type": "tool_call", "actionType": action}
    if file_path:
        payload["filePath"] = file_path
    if command:
        payload["args"] = {"command": command}
    return {"type": "tool_call", "timestamp": None, "payload": payload}


def _ev(etype, **payload):
    payload["type"] = etype
    return {"type": etype, "timestamp": payload.pop("ts", None), "payload": payload}


def _fixture() -> dict:
    """Uma sessão com dois vocabulários, um Clear, créditos e uma rejeição."""
    events = [
        _ev("user", content="Implemente o parser de eventos do Kiro por favor"),
        _ev("turn_start"),
        # descoberta em snake_case (novo vocabulário)
        _tool_call("read_files", file_path="a.py"),
        _tool_call("grep_search", command="grep foo a.py"),
        # implementação em camelCase (vocabulário antigo)
        _tool_call("write", file_path="a.py"),
        _tool_call("str_replace", file_path="a.py"),  # 2a edição no mesmo arquivo → rework
        # actionType desconhecido → alimenta o canário
        _tool_call("teleport_files", file_path="a.py"),
        _ev("tool_result", success=True, content="ok"),
        # Kiro 1.0.395: outcome é sempre "selected"; a escolha real vem em selectedOption
        _ev("interaction_resolved", outcome="selected", selectedOption="reject"),  # rejeição 🟢
        _ev("interaction_resolved", outcome="selected", selectedOption="always-accept"),
        # tombstone: sumarização de contexto (nova versão)
        _ev("tombstone", kind="summarization", metadata={"truncatedMessageCount": 42}),
        _ev("turn_end", stopReason="end_turn"),
        _ev("usage_summary", elapsedTime=45000,
            promptTurnSummaries=[{"unit": "credit", "usage": 0.5, "usedTools": ["read_file"]}]),
        # alucinação intra-sessão: afirma path e a ferramenta desmente perto
        _ev("assistant", content="O arquivo `models/User.java` já existe."),
        _ev("tool_result", success=False,
            content="Error: No such file or directory: models/User.java"),
        _ev("turn_end", stopReason="cancelled"),  # turno abortado 🟢
    ]
    return {
        "_type": "harness-metrics-intermediate",
        "period": {"from": "2026-08-01", "to": "2026-08-31"},
        "scope": {"workspace": "ALL"},
        "sessions": [{
            "sessionId": "sess-1",
            "surface": "ide",
            "agentMode": "vibe",
            "workspacePaths": ["/Users/dev/proj"],
            "createdAt": "2026-08-10T10:00:00Z",
            "lastModifiedAt": "2026-08-10T10:05:00Z",
            "events": events,
        }],
    }


def check(name, cond, extra=""):
    if not cond:
        print(f"FAIL: {name} {extra}", file=sys.stderr)
        raise SystemExit(1)
    print(f"ok: {name}")


def main() -> int:
    # 1) classificação resiliente aos dois vocabulários
    check("read_files é discovery", actions.is_discovery({"actionType": "read_files"}))
    check("readFiles é discovery", actions.is_discovery({"actionType": "readFiles"}))
    check("write é impl", actions.is_implementation({"actionType": "write"}))
    check("fs_write é impl", actions.is_implementation({"actionType": "fs_write"}))
    check("teleport_files é unknown",
          actions.classify_action({"actionType": "teleport_files"}) == actions.UNKNOWN)
    # fallback por verbo: MCP e ferramentas de processo sem alias explícito
    check("mcp get é discovery",
          actions.is_discovery({"actionType": "mcp_github_get_file_contents"}))
    check("mcp push é other (não impl)",
          actions.classify_action({"actionType": "mcp_github_push_files"}) == actions.OTHER)
    check("getProcessOutput é discovery",
          actions.is_discovery({"actionType": "getProcessOutput"}))
    check("controlProcess é other",
          actions.classify_action({"actionType": "controlProcess"}) == actions.OTHER)
    check("verbo desconhecido segue unknown",
          actions.classify_action({"actionType": "frobnicate_widget"}) == actions.UNKNOWN)

    data = _fixture()
    seg.segment(data)
    tasks = data["sessions"][0]["tasks"]

    # 2) segmentação: a 1a (e única) tarefa NÃO pode ser confidence:low
    check("1a tarefa não é low", tasks[0]["confidence"] != "low",
          f'(confidence={tasks[0]["confidence"]})')
    check("segmentation version 1.0.0", data["_segmentation"]["version"] == "1.0.0")

    det = md.compute(data)
    m = det["metrics"]

    # 3) canário conta o actionType desconhecido
    unm = det["unmappedActionTypes"]
    check("canário pegou teleport_files", "teleport_files" in unm["byType"], str(unm))

    # 4) discovery/impl contados via aliases (2 discovery, 2 impl; unknown não conta)
    cde = m["context_discovery_effort"]["detail"]
    check("discovery=2", cde["discovery"] == 2, str(cde))
    check("implementation=2", cde["implementation"] == 2, str(cde))

    # 5) créditos e tempo lidos
    check("créditos lidos", "credits_used" in m and m["credits_used"]["value"] == 0.5)
    check("elapsed lido", "elapsed_seconds" in m and m["elapsed_seconds"]["value"] == 45.0)

    # 6) rejeição (via selectedOption, formato 1.0.395) e turno abortado como 🟢
    check("rejeição contada (selectedOption)", m["tool_rejection_rate"]["detail"]["rejections"] == 1)
    check("always-accept contado", m["tool_rejection_rate"]["detail"]["alwaysAccepts"] == 1)
    check("turno abortado contado", m["aborted_turn_rate"]["detail"]["abortedTurns"] == 1)

    # 6b) truncamento de contexto (tombstone, nova versão)
    check("truncation métrica existe", "context_truncation" in m, list(m))
    ct = m["context_truncation"]["detail"]
    check("truncatedMessages=42", ct["truncatedMessages"] == 42, str(ct))
    check("truncationEvents=1", ct["truncationEvents"] == 1, str(ct))

    # 7) hallucination como TAXA por tarefa (não contagem), com bruto no detail
    h = m["hallucination_intrasession"]
    check("halluc detail.events=1", h["detail"]["events"] == 1, str(h["detail"]))
    check("halluc value é taxa <=1", h["value"] is not None and 0 < h["value"] <= 1, str(h))

    # 8) exemplo de falha NÃO contém stdout cru (privacidade)
    ex = m["tool_failure_rate"]["example"] or ""
    check("exemplo de falha sem stdout cru", "No such file" not in ex, ex)

    # 9) trend roda e normaliza hallucination_semantic por tarefa
    tr = mt.compute(data)["metrics"]
    hs = tr["hallucination_semantic"]
    check("hallucination_semantic é taxa", hs["value"] is None or hs["value"] <= 1, str(hs))

    print("\nTODOS OS TESTES PASSARAM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
