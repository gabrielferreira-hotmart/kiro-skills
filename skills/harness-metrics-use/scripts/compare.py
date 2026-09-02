#!/usr/bin/env python3
"""compare.py — compara dois snapshots (baseline vs after) → report.json.

Ver references/baseline-after.md.

Regras de comparação válida:
  - mesma fórmula nas métricas derivadas (senão: warning, não compara a derivada)
  - mesma versão de skill (senão: warning)
  - comparar 🟢 com 🟢 e 🟡 com 🟡 (a classe vem do próprio snapshot)

Para cada métrica: valor baseline, valor after, Δ absoluto, Δ%, class, n de cada lado,
e um "direction" (better/worse/flat) segundo a semântica da métrica.

Uso:
    python3 compare.py --baseline snapshots/baseline.json \
        --after snapshots/after.json --out report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# para cada métrica, se aumentar é bom (+1) ou ruim (-1)
DIRECTION_GOOD = {
    "turns_to_resolution": -1,
    "tool_failure_rate": -1,
    "context_discovery_effort": -1,
    "context_usage": -1,
    "rework_rate": -1,
    "hallucination_intrasession": -1,
    "human_correction_rate": -1,
    "first_pass_resolution": +1,
    "hallucination_semantic": -1,
    "resolution_efficiency": +1,
}

SMALL_SAMPLE = 10


def _delta_pct(base, after):
    if base in (None, 0) or after is None:
        return None
    return round((after - base) / abs(base) * 100.0, 1)


def _direction(key, base, after):
    if base is None or after is None:
        return "n/a"
    if after == base:
        return "flat"
    improved = (after > base) == (DIRECTION_GOOD.get(key, +1) > 0)
    return "better" if improved else "worse"


def main() -> int:
    ap = argparse.ArgumentParser(description="Compara baseline vs after")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))

    warnings = []
    if base.get("skillVersion") != after.get("skillVersion"):
        warnings.append(
            f"skillVersion difere: {base.get('skillVersion')} vs {after.get('skillVersion')}"
        )
    if base.get("derivedFormula") != after.get("derivedFormula"):
        warnings.append("fórmula de métrica derivada difere — Δ de resolution_efficiency não confiável")
    for snap, lbl in ((base, "baseline"), (after, "after")):
        tc = snap.get("taskCount") or 0
        if tc < SMALL_SAMPLE:
            warnings.append(f"amostra pequena em {lbl}: {tc} tarefas (< {SMALL_SAMPLE})")

    diffs = {}
    bm = base.get("metrics", {})
    am = after.get("metrics", {})
    for key in sorted(set(bm) | set(am)):
        b = bm.get(key, {})
        a = am.get(key, {})
        bv, av = b.get("value"), a.get("value")
        cls_b, cls_a = b.get("class"), a.get("class")
        if cls_b and cls_a and cls_b != cls_a:
            warnings.append(f"classe difere para {key}: {cls_b} vs {cls_a}")
        diffs[key] = {
            "class": cls_b or cls_a,
            "baseline": bv,
            "after": av,
            "delta": (round(av - bv, 4) if isinstance(bv, (int, float)) and isinstance(av, (int, float)) else None),
            "deltaPct": _delta_pct(bv, av),
            "direction": _direction(key, bv, av),
            "nBaseline": b.get("n"),
            "nAfter": a.get("n"),
        }

    report = {
        "_type": "harness-metrics-report",
        "baselineLabel": base.get("label"),
        "afterLabel": after.get("label"),
        "scope": after.get("scope") or base.get("scope"),
        "period": {"baseline": base.get("period"), "after": after.get("period")},
        "taskCount": {"baseline": base.get("taskCount"), "after": after.get("taskCount")},
        "warnings": warnings,
        "diffs": diffs,
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[compare] {len(diffs)} métricas | {len(warnings)} avisos", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
