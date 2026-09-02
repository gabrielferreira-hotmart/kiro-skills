#!/usr/bin/env python3
"""metrics_trend.py — métricas 🟡 (tendência / indicador, comparação relativa).

Ver references/metric-definitions.md (seção Tendência).

Heurística LOCAL, sem LLM. A variante com judge externo vive em semantic_eval.py.

Calcula:
  - human_correction_rate    (correções do usuário por tarefa)
  - first_pass_resolution    (% tarefas sem correção após 1ª entrega)
  - hallucination_semantic   (correção factual do usuário por tarefa — sem LLM)
  - resolution_efficiency    (derivada; fórmula explícita no output)

IMPORTANTE: valores 🟡 são tendências, nunca absolutos. Todas carregam class=trend e
confidence, e a apresentação marca com legenda.

Uso:
    python3 metrics_trend.py --in intermediate.segmented.json --out metrics.trend.json
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

# correção genérica (entendimento/direção)
CORRECTION_RE = re.compile(
    r"\b("
    r"não é isso|nao e isso|não foi isso|nao foi isso|"
    r"volt[ae]\b|revert|desfaz|desfaç|refaz|refaça|de novo|novamente|"
    r"você entendeu errado|voce entendeu errado|entendeu errado|não era isso|nao era isso|"
    r"corrig|não faça|nao faca|"
    r"that's not|thats not|undo|revert|redo|not what i|wrong"
    r")\b",
    re.IGNORECASE,
)

# correção FACTUAL (nega um fato afirmado pela IA) → hallucination semântica
FACT_CORRECTION_RE = re.compile(
    r"\b("
    r"esse arquivo não existe|isso não existe|não existe|nao existe|"
    r"esse método não existe|essa classe não existe|não tem esse|nao tem esse|"
    r"na verdade (é|e|são|sao|não|nao)|"
    r"isso está errado|isso esta errado|está incorreto|esta incorreto|"
    r"doesn'?t exist|that'?s wrong|actually it'?s|incorrect"
    r")\b",
    re.IGNORECASE,
)


def _user_text(payload: dict) -> str:
    c = payload.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = [b.get("text") or b.get("data") or "" for b in c if isinstance(b, dict)]
        return " ".join(p for p in parts if isinstance(p, str))
    return ""


def _compute_metrics(sessions: list[dict]) -> tuple[dict, int]:
    """Núcleo do cálculo de tendência sobre uma lista de sessões.

    Retorna (metrics, tasks_total). Extraído para permitir breakdown por workspace.
    """
    data = {"sessions": sessions}
    tasks_total = 0
    correction_count = 0
    fact_correction_count = 0
    tasks_with_correction = 0

    # para resolution_efficiency precisamos de sinais agregados
    turn_counts: list[int] = []

    # primeiro exemplo de evidência por métrica (truncado depois na anonimização)
    ex_correction = None       # texto de uma correção do usuário
    ex_fact_correction = None  # texto de uma correção factual
    ex_first_pass = None       # abertura de uma tarefa resolvida de primeira

    for session in data.get("sessions", []):
        events = session.get("events", [])
        tasks = session.get("tasks", [])
        tasks_total += len(tasks)

        for t in tasks:
            turn_counts.append(t.get("turnCount", 0))
            start, end = t.get("startIdx", 0), t.get("endIdx", 0)
            task_has_correction = False
            first_user_seen = False
            for e in events[start : end + 1]:
                if e.get("type") != "user":
                    continue
                text = _user_text(e.get("payload", {}))
                if not first_user_seen:
                    first_user_seen = True
                    continue  # abertura não é correção
                if CORRECTION_RE.search(text):
                    correction_count += 1
                    task_has_correction = True
                    if ex_correction is None:
                        ex_correction = text.strip()[:160]
                if FACT_CORRECTION_RE.search(text):
                    fact_correction_count += 1
                    if ex_fact_correction is None:
                        ex_fact_correction = text.strip()[:160]
            if task_has_correction:
                tasks_with_correction += 1
            elif ex_first_pass is None:
                ex_first_pass = t.get("openingPrompt", "")[:120]

    def _num(v):
        return round(v, 4) if isinstance(v, float) else v

    first_pass = (
        (tasks_total - tasks_with_correction) / tasks_total if tasks_total else None
    )
    human_corr_rate = correction_count / tasks_total if tasks_total else None

    # resolution_efficiency (variante A, explícita): first_pass ponderado pelo esforço.
    # esforço_norm = média de turns normalizada + taxa de correção.
    mean_turns = statistics.mean(turn_counts) if turn_counts else 0.0
    effort = (mean_turns / 10.0) + (human_corr_rate or 0.0)  # normalização simples
    res_eff = None
    if first_pass is not None:
        res_eff = first_pass / (1.0 + effort)  # ∈ (0,1], penaliza esforço

    confidence = "low" if tasks_total < 10 else "medium"

    metrics = {
        "human_correction_rate": {
            "key": "human_correction_rate",
            "value": _num(human_corr_rate),
            "class": "trend",
            "n": tasks_total,
            "confidence": confidence,
            "notes": ["heurística local; frases-âncora multilíngues (sinal fraco)"],
            "detail": {"corrections": correction_count, "tasks": tasks_total},
            "example": (
                f'Correção detectada: "{ex_correction}"' if ex_correction
                else "Nenhuma correção detectada no período."
            ),
        },
        "first_pass_resolution": {
            "key": "first_pass_resolution",
            "value": _num(first_pass),
            "class": "trend",
            "n": tasks_total,
            "confidence": confidence,
            "notes": ["% tarefas sem correção após 1ª entrega (consome sinal 🟡)"],
            "detail": {"tasksWithCorrection": tasks_with_correction, "tasks": tasks_total},
            "example": (
                f'Ex. resolvida de primeira: "{ex_first_pass}"' if ex_first_pass else None
            ),
        },
        "hallucination_semantic": {
            "key": "hallucination_semantic",
            # normalizado por tarefa (review): contagem absoluta enganava Δ% entre
            # períodos de tamanhos diferentes. detail.factCorrections mantém o bruto.
            "value": _num(fact_correction_count / tasks_total) if tasks_total else None,
            "class": "trend",
            "n": tasks_total,
            "confidence": confidence,
            "notes": ["correção factual do usuário por tarefa (sem LLM); complementa a 🟢"],
            "detail": {"factCorrections": fact_correction_count, "tasks": tasks_total},
            "example": (
                f'Correção factual: "{ex_fact_correction}"' if ex_fact_correction
                else "Nenhuma correção factual detectada."
            ),
        },
        "resolution_efficiency": {
            "key": "resolution_efficiency",
            "value": _num(res_eff),
            "class": "trend",
            "n": tasks_total,
            "confidence": confidence,
            "notes": ["derivada; herda 🟡"],
            "detail": {
                "formula": "first_pass / (1 + (mean_turns/10 + human_correction_rate))",
                "meanTurns": _num(mean_turns),
                "effort": _num(effort),
            },
            "example": (
                f'first_pass {_num(first_pass)} ÷ esforço (turnos médios {_num(mean_turns)} '
                f'+ correções {_num(human_corr_rate)})'
                if first_pass is not None else None
            ),
        },
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

    by_repo = {}
    repo_groups = _group_by(sessions, _workspace_of)
    if len(repo_groups) > 1:
        for ws, sess in repo_groups.items():
            m, tc = _compute_metrics(sess)
            by_repo[ws] = {"taskCount": tc, "metrics": m}

    by_mode = {}
    mode_groups = _group_by(sessions, lambda s: s.get("agentMode") or "?")
    if len(mode_groups) > 1:
        for mode, sess in mode_groups.items():
            m, tc = _compute_metrics(sess)
            by_mode[mode] = {"taskCount": tc, "metrics": m}

    return {
        "_type": "harness-metrics-trend",
        "period": data.get("period"),
        "scope": data.get("scope"),
        "taskCount": tasks_total,
        "metrics": metrics,
        "byRepo": by_repo,
        "byMode": by_mode,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Métricas de tendência (🟡)")
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.in_path).read_text(encoding="utf-8"))
    result = compute(data)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[metrics_trend] {result['taskCount']} tarefas (heurística local, sem LLM)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
