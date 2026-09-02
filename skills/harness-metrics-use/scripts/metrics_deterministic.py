#!/usr/bin/env python3
"""metrics_deterministic.py — métricas 🟢 (fato reprodutível).

Ver references/metric-definitions.md (seção Determinísticas).

Calcula, a partir do intermediate.segmented.json:
  - turns_to_resolution         (média/mediana de turnCount por tarefa)
  - tool_failure_rate           (bruto + calibrado com allowlist de exit codes benignos)
  - context_discovery_effort    (ratio descoberta:implementação — via actions.py)
  - context_usage               (média/pico de contextUsage.usagePercentage)
  - rework_rate                 (edições repetidas no mesmo arquivo + reverts)
  - hallucination_intrasession  (afirmação de path contradita por tool_result; por tarefa)
  - tool_rejection_rate         (interaction_resolved selectedOption=reject — correção 🟢)
  - aborted_turn_rate           (stopReason cancelled/failed/aborted por tarefa)
  - context_truncation          (tombstone kind=summarization — pressão de contexto)
  - credits_used                (promptTurnSummaries.usage — quando presente)
  - elapsed_seconds             (usage_summary.elapsedTime — tempo real de execução)

Cada métrica sai com:
  { "key", "value", "class": "deterministic", "n", "notes": [...], "detail": {...} }

Classificação de actionType é resiliente a camelCase/snake_case (ver actions.py) e
o resultado inclui `unmappedActionTypes` como canário de mudança de vocabulário.

Uso:
    python3 metrics_deterministic.py --in intermediate.segmented.json \
        --out metrics.deterministic.json
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

try:
    from actions import classify_action, unmapped_summary, DISCOVERY, IMPLEMENTATION
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from actions import classify_action, unmapped_summary, DISCOVERY, IMPLEMENTATION

# --- Tool Failure Rate: calibragem de exit codes benignos --------------------
BENIGN_MARKERS = [
    "No such file or directory",
    "Directory not empty",
    "did not match any files",
    "nothing to commit",
]

# stopReasons que indicam turno interrompido / mal-sucedido (sinal 🟢 de dificuldade)
ABORTED_STOP_REASONS = {"cancelled", "canceled", "failed", "aborted", "error", "max_tokens"}


def _result_content_str(payload: dict) -> str:
    c = payload.get("content")
    return c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)


def _toolcall_summary(payload: dict) -> str:
    """Resumo curto e legível de um tool_call para exemplo.

    Privacidade: para exemplos NUNCA usamos o conteúdo de tool_result (stdout/stderr
    cru). Aqui usamos só o comando/arquivo do próprio tool_call, que é menos sensível,
    e ainda assim truncado. Ver references/privacy.md.
    """
    at = payload.get("actionType")
    args = payload.get("args")
    cmd = ""
    if isinstance(args, str):
        try:
            cmd = json.loads(args).get("command", "")
        except (json.JSONDecodeError, AttributeError):
            cmd = args
    elif isinstance(args, dict):
        cmd = args.get("command", "")
    if cmd:
        return cmd[:100]
    fp = payload.get("filePath")
    return f"{at} {fp}" if fp else str(at)


def _is_benign_failure(content: str) -> bool:
    return any(m in content for m in BENIGN_MARKERS)


# --- Hallucination intra-sessão ----------------------------------------------
CODE_EXT = (
    r"java|py|ts|tsx|js|jsx|md|yml|yaml|json|xml|sh|sql|html|css|go|rb|kt|properties|txt|toml|cfg"
)
PATH_CLAIM_RE = re.compile(
    rf"`("
    rf"[\w./\-]+/[\w.\-]+"          # tem barra: parece caminho
    rf"|[\w.\-]+\.(?:{CODE_EXT})"    # ou termina em extensão de código conhecida
    rf")`"
)
PATH_MISS_RE = re.compile(r"(No such file|did not match|não existe|not found|cannot find)", re.IGNORECASE)

PROXIMITY_WINDOW = 60  # chars entre o marcador de erro e o nome do arquivo


def _miss_near_file(content: str, file_base: str) -> bool:
    """True se um marcador 'arquivo não encontrado' aparece PERTO do nome do arquivo."""
    if file_base not in content:
        return False
    for m in PATH_MISS_RE.finditer(content):
        start = m.start()
        window = content[max(0, start - PROXIMITY_WINDOW): start + PROXIMITY_WINDOW]
        if file_base in window:
            return True
    return False


def _iter_events(session: dict):
    return session.get("events", [])


def _compute_metrics(sessions: list[dict]) -> tuple[dict, int]:
    """Núcleo do cálculo determinístico sobre uma lista de sessões.

    Retorna (metrics, tasks_total). Extraído para poder ser chamado tanto no
    conjunto todo quanto por grupo (workspace ou agentMode).
    """
    data = {"sessions": sessions}
    turn_counts: list[int] = []
    tool_total = 0
    tool_fail_raw = 0
    tool_fail_calibrated = 0
    discovery = 0
    implementation = 0
    ctx_samples: list[float] = []
    rework_events = 0
    halluc_events = 0
    tasks_total = 0
    # sinais 🟢 de graça (review): rejeição de ferramenta e turnos abortados
    interactions_total = 0
    rejections = 0
    turns_total = 0
    aborted_turns = 0
    # tempo/custo reais (review bloqueador 2)
    credits_used = 0.0
    credit_sessions = 0
    elapsed_samples: list[float] = []
    # sinais da nova versão (Kiro 1.0.395): truncamento/sumarização de contexto
    truncation_events = 0
    truncated_messages = 0
    sessions_with_truncation = set()
    always_accepts = 0  # 'always-accept' vs 'accept' (fadiga de aprovação)

    ex_halluc = None
    ex_tool_fail = None
    ex_rework = None
    ex_discovery = None
    ex_turns = None
    ex_reject = None
    ex_trunc = None

    for session in data.get("sessions", []):
        events = _iter_events(session)
        tasks = session.get("tasks", [])
        tasks_total += len(tasks)
        for t in tasks:
            tc = t.get("turnCount", 0)
            turn_counts.append(tc)
            if ex_turns is None or tc > ex_turns.get("turns", -1):
                ex_turns = {"openingPrompt": t.get("openingPrompt", ""), "turns": tc}

        file_edit_count: dict[str, int] = {}
        recent_claim: str | None = None

        for e in events:
            p = e.get("payload", {})
            etype = e.get("type")

            if etype == "assistant":
                txt = p.get("content") if isinstance(p.get("content"), str) else ""
                claims = PATH_CLAIM_RE.findall(txt or "")
                recent_claim = claims[-1] if claims else recent_claim

            elif etype == "tool_call":
                cat = classify_action(p)
                if cat == DISCOVERY:
                    discovery += 1
                    summ = _toolcall_summary(p)
                    if summ and len(summ) > 4 and (ex_discovery is None or
                                                    len(ex_discovery["command"]) <= 4):
                        ex_discovery = {"command": summ}
                elif cat == IMPLEMENTATION:
                    implementation += 1
                    fp = p.get("filePath")
                    if fp:
                        file_edit_count[fp] = file_edit_count.get(fp, 0) + 1
                        if file_edit_count[fp] > 1:
                            rework_events += 1
                            if ex_rework is None:
                                ex_rework = {"file": fp, "edits": file_edit_count[fp]}

            elif etype == "tool_result":
                tool_total += 1
                content = _result_content_str(p)
                if p.get("success") is False:
                    tool_fail_raw += 1
                    if not _is_benign_failure(content):
                        tool_fail_calibrated += 1
                        # Privacidade: NÃO guardamos stdout/stderr cru. O exemplo usa
                        # só a categoria de falha, sem conteúdo do tool_result.
                        if ex_tool_fail is None:
                            ex_tool_fail = {"tool": str(p.get("toolName") or "comando")}
                if recent_claim:
                    claim_base = recent_claim.rsplit("/", 1)[-1]
                    if claim_base and _miss_near_file(content, claim_base):
                        halluc_events += 1
                        if ex_halluc is None:
                            # exemplo: só o path afirmado (do próprio log da IA), sem
                            # despejar o conteúdo do tool_result.
                            ex_halluc = {"claim": recent_claim}
                        recent_claim = None

            elif etype == "turn_end":
                turns_total += 1
                sr = str(p.get("stopReason") or "").lower()
                if sr in ABORTED_STOP_REASONS:
                    aborted_turns += 1

            elif etype == "interaction_resolved":
                interactions_total += 1
                # Kiro 1.0.395: `outcome` passou a ser sempre "selected"; a escolha real
                # (accept | always-accept | reject | deny) vem em `selectedOption`.
                # Antes líamos só `outcome`, o que zerava rejeições na nova versão.
                option = str(p.get("selectedOption") or p.get("outcome") or "").lower()
                if "reject" in option or "deny" in option or option in ("no", "cancel"):
                    rejections += 1
                    if ex_reject is None:
                        ex_reject = {"option": option or "reject"}
                elif "always" in option:
                    always_accepts += 1

            elif etype == "tombstone":
                # Kiro 1.0.395: sumarização/truncamento de contexto. É pressão de
                # contexto direta (mais confiável que o contextUsage amostrado).
                if str(p.get("kind")) == "summarization":
                    truncation_events += 1
                    sessions_with_truncation.add(id(session))
                    meta = p.get("metadata") or {}
                    tmc = meta.get("truncatedMessageCount")
                    if isinstance(tmc, (int, float)):
                        truncated_messages += int(tmc)
                        if ex_trunc is None or tmc > ex_trunc.get("count", -1):
                            ex_trunc = {"count": int(tmc)}

            elif etype == "session_metadata":
                if p.get("key") == "contextUsage":
                    val = (p.get("value") or {}).get("usagePercentage")
                    if isinstance(val, (int, float)):
                        ctx_samples.append(float(val))

            elif etype == "usage_summary":
                et = p.get("elapsedTime")
                if isinstance(et, (int, float)) and et > 0:
                    elapsed_samples.append(float(et) / 1000.0)  # ms → s
                summaries = p.get("promptTurnSummaries")
                if isinstance(summaries, list) and summaries:
                    sess_credits = 0.0
                    found = False
                    for row in summaries:
                        if not isinstance(row, dict):
                            continue
                        if str(row.get("unit")) == "credit" and isinstance(row.get("usage"), (int, float)):
                            sess_credits += float(row["usage"])
                            found = True
                    if found:
                        credits_used += sess_credits
                        credit_sessions += 1

            meta = p.get("_meta") or {}
            if isinstance(meta, dict):
                ck = (meta.get("kiro") or {}).get("checkpoint")
                if ck and etype == "tool_result" and p.get("success") is False:
                    rework_events += 1

    def _num(v):
        return round(v, 4) if isinstance(v, float) else v

    metrics = {
        "turns_to_resolution": {
            "key": "turns_to_resolution",
            "value": _num(statistics.mean(turn_counts)) if turn_counts else None,
            "class": "deterministic",
            "n": len(turn_counts),
            "notes": [],
            "detail": {
                "mean": _num(statistics.mean(turn_counts)) if turn_counts else None,
                "median": _num(statistics.median(turn_counts)) if turn_counts else None,
                "max": max(turn_counts) if turn_counts else None,
            },
            "example": (
                f'Tarefa com mais turnos ({ex_turns["turns"]}): "{ex_turns["openingPrompt"]}"'
                if ex_turns and ex_turns.get("turns") else None
            ),
        },
        "tool_failure_rate": {
            "key": "tool_failure_rate",
            "value": _num(tool_fail_calibrated / tool_total) if tool_total else None,
            "class": "deterministic",
            "n": tool_total,
            "notes": ["calibrado (exit codes benignos ignorados)"],
            "detail": {
                "totalTools": tool_total,
                "failRaw": tool_fail_raw,
                "failCalibrated": tool_fail_calibrated,
                "rateRaw": _num(tool_fail_raw / tool_total) if tool_total else None,
            },
            "example": (
                f'Falha na ferramenta "{ex_tool_fail["tool"]}"' if ex_tool_fail else None
            ),
        },
        "context_discovery_effort": {
            "key": "context_discovery_effort",
            "value": _num(discovery / implementation) if implementation else None,
            "class": "deterministic",
            "n": discovery + implementation,
            "notes": ["ratio descoberta:implementação"],
            "detail": {"discovery": discovery, "implementation": implementation},
            "example": (
                f'Ação de descoberta: {ex_discovery["command"]}' if ex_discovery else None
            ),
        },
        "context_usage": {
            "key": "context_usage",
            "value": _num(statistics.mean(ctx_samples)) if ctx_samples else None,
            "class": "deterministic",
            "n": len(ctx_samples),
            "notes": ["amostrado (contextUsage.usagePercentage)"],
            "detail": {
                "mean": _num(statistics.mean(ctx_samples)) if ctx_samples else None,
                "peak": _num(max(ctx_samples)) if ctx_samples else None,
            },
            "example": (
                f'Pico de uso da janela: {_num(max(ctx_samples)):.0f}%'
                if ctx_samples else None
            ),
        },
        "rework_rate": {
            "key": "rework_rate",
            "value": _num(rework_events / tasks_total) if tasks_total else None,
            "class": "deterministic",
            "n": tasks_total,
            "notes": ["edições repetidas no mesmo arquivo + reverts por tarefa"],
            "detail": {"reworkEvents": rework_events, "tasks": tasks_total},
            "example": (
                f'Arquivo reeditado {ex_rework["edits"]}× na mesma tarefa: {ex_rework["file"]}'
                if ex_rework else None
            ),
        },
        "hallucination_intrasession": {
            "key": "hallucination_intrasession",
            # normalizado por tarefa (review): contagem absoluta enganava Δ% entre
            # períodos de tamanhos diferentes. detail.events mantém o bruto.
            "value": _num(halluc_events / tasks_total) if tasks_total else None,
            "class": "deterministic",
            "n": tasks_total,
            "notes": ["afirmação de path contradita por tool_result; taxa por tarefa"],
            "detail": {"events": halluc_events, "tasks": tasks_total},
            "example": (
                f'Afirmou que "{ex_halluc["claim"]}" existia, mas a ferramenta não encontrou'
                if ex_halluc else None
            ),
        },
        "tool_rejection_rate": {
            "key": "tool_rejection_rate",
            "value": _num(rejections / interactions_total) if interactions_total else None,
            "class": "deterministic",
            "n": interactions_total,
            "notes": ["selectedOption=reject — correção humana determinística"],
            "detail": {
                "rejections": rejections,
                "interactions": interactions_total,
                "alwaysAccepts": always_accepts,
            },
            "example": (
                f'Você rejeitou uma ação proposta (opção "{ex_reject["option"]}")'
                if ex_reject else None
            ),
        },
        "aborted_turn_rate": {
            "key": "aborted_turn_rate",
            "value": _num(aborted_turns / turns_total) if turns_total else None,
            "class": "deterministic",
            "n": turns_total,
            "notes": ["turnos com stopReason cancelled/failed/aborted"],
            "detail": {"abortedTurns": aborted_turns, "turns": turns_total},
            "example": None,
        },
    }

    # tempo e custo reais — só entram quando o dado existe (versões novas do Kiro)
    if elapsed_samples:
        metrics["elapsed_seconds"] = {
            "key": "elapsed_seconds",
            "value": _num(statistics.median(elapsed_samples)),
            "class": "deterministic",
            "n": len(elapsed_samples),
            "notes": ["usage_summary.elapsedTime (mediana, s)"],
            "detail": {
                "median": _num(statistics.median(elapsed_samples)),
                "mean": _num(statistics.mean(elapsed_samples)),
                "total": _num(sum(elapsed_samples)),
            },
            "example": f"Tempo mediano de execução por turno: {statistics.median(elapsed_samples):.0f}s",
        }
    if credit_sessions:
        metrics["credits_used"] = {
            "key": "credits_used",
            "value": _num(credits_used),
            "class": "deterministic",
            "n": credit_sessions,
            "notes": [
                "promptTurnSummaries.usage (unit=credit)",
                "não validado contra 'Est. Credits Used' da UI — tratar como aproximação",
            ],
            "detail": {"totalCredits": _num(credits_used), "sessionsWithCredits": credit_sessions},
            "example": f"~{credits_used:.1f} créditos somados em {credit_sessions} sessões",
        }
    # truncamento/sumarização de contexto (Kiro 1.0.395+, evento tombstone) — só quando
    # o dado existe. Média de mensagens truncadas por sessão = pressão de contexto direta.
    if truncation_events:
        metrics["context_truncation"] = {
            "key": "context_truncation",
            "value": _num(truncation_events / len(sessions)) if sessions else None,
            "class": "deterministic",
            "n": len(sessions),
            "notes": ["tombstone kind=summarization — sumarizações por sessão"],
            "detail": {
                "truncationEvents": truncation_events,
                "truncatedMessages": truncated_messages,
                "sessionsWithTruncation": len(sessions_with_truncation),
                "sessions": len(sessions),
            },
            "example": (
                f'Maior sumarização descartou {ex_trunc["count"]} mensagens do contexto'
                if ex_trunc else None
            ),
        }

    return metrics, tasks_total


def _workspace_of(session: dict) -> str:
    paths = session.get("workspacePaths") or []
    if paths and isinstance(paths, list):
        return paths[0]
    return "(desconhecido)"


def _group_by(sessions: list, key_fn) -> dict:
    groups: dict[str, list] = {}
    for s in sessions:
        groups.setdefault(key_fn(s), []).append(s)
    return groups


def compute(data: dict) -> dict:
    sessions = data.get("sessions", [])
    metrics, tasks_total = _compute_metrics(sessions)

    # breakdown por repositório (workspace) — só quando há mais de um
    by_repo = {}
    repo_groups = _group_by(sessions, _workspace_of)
    if len(repo_groups) > 1:
        for ws, sess in repo_groups.items():
            m, tc = _compute_metrics(sess)
            by_repo[ws] = {"taskCount": tc, "metrics": m}

    # breakdown por agentMode (vibe/spec/cli) — barato e acionável (review)
    by_mode = {}
    mode_groups = _group_by(sessions, lambda s: s.get("agentMode") or "?")
    if len(mode_groups) > 1:
        for mode, sess in mode_groups.items():
            m, tc = _compute_metrics(sess)
            by_mode[mode] = {"taskCount": tc, "metrics": m}

    return {
        "_type": "harness-metrics-deterministic",
        "period": data.get("period"),
        "scope": data.get("scope"),
        "taskCount": tasks_total,
        "metrics": metrics,
        "byRepo": by_repo,
        "byMode": by_mode,
        # canário de mudança de vocabulário de actionType (review bloqueador 1)
        "unmappedActionTypes": unmapped_summary(sessions),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Métricas determinísticas (🟢)")
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.in_path).read_text(encoding="utf-8"))
    result = compute(data)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    unm = result["unmappedActionTypes"]
    warn = ""
    if unm["ratio"] >= 0.2:
        warn = (f" ⚠ {unm['ratio']*100:.0f}% dos tool_calls com actionType não mapeado "
                f"(vocabulário do Kiro pode ter mudado): {list(unm['byType'])[:5]}")
    print(f"[metrics_deterministic] {result['taskCount']} tarefas processadas{warn}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
