#!/usr/bin/env python3
"""snapshot.py — congela métricas de um período num arquivo imutável <label>.json.

Ver references/baseline-after.md.

O snapshot contém tudo que compare.py precisa para uma comparação válida:
  - versão da skill + versão do Kiro (quem detecta quebra de formato) + schemaVersion
  - range from/to + label + scope (workspace)
  - nº de sessões e nº de tarefas
  - hash do input (detecta comparação inválida / drift)
  - fórmula das métricas derivadas (extraída do detail de resolution_efficiency)
  - todas as métricas com class (🟢/🟡)
  - byMode (vibe/spec/cli) e unmappedActionTypes (canário de vocabulário)

Uso:
    python3 snapshot.py --label baseline \
        --deterministic metrics.deterministic.json \
        --trend metrics.trend.json \
        [--semantic metrics.semantic.json] \
        --out ./.harness-metrics/snapshots/baseline.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# versão única da skill — mantida em sincronia com o frontmatter do SKILL.md.
SKILL_VERSION = "1.0.0"


def _detect_kiro_version() -> str | None:
    """Melhor esforço para descobrir a versão do Kiro instalada.

    A versão do Kiro (não o schemaVersion, que se mostrou instável) é o que permite
    correlacionar um snapshot com uma quebra de formato. Ordem de tentativa:
      1. env KIRO_VERSION (override explícito);
      2. product.json do app instalado (fonte real — ex: version 1.0.395);
      3. arquivos soltos ~/.kiro/version (fallback legado).
    Se nada achar, devolve None e o snapshot registra 'unknown'.
    """
    import os
    import json as _json

    env = os.environ.get("KIRO_VERSION")
    if env:
        return env.strip()

    # product.json do app instalado (macOS, Linux, Windows)
    product_paths = [
        "/Applications/Kiro.app/Contents/Resources/app/product.json",
        os.path.expanduser("~/Applications/Kiro.app/Contents/Resources/app/product.json"),
        "/usr/share/kiro/resources/app/product.json",
        "/opt/Kiro/resources/app/product.json",
        os.path.expanduser("~/AppData/Local/Programs/Kiro/resources/app/product.json"),
    ]
    for p in product_paths:
        try:
            with open(p, encoding="utf-8") as fh:
                d = _json.load(fh)
            v = d.get("version") or d.get("kiroVersion")
            if v:
                return str(v).strip()
        except (OSError, ValueError):
            continue

    for c in (os.path.expanduser("~/.kiro/version"), os.path.expanduser("~/.kiro/VERSION")):
        try:
            with open(c, encoding="utf-8") as fh:
                v = fh.read().strip()
                if v:
                    return v
        except OSError:
            continue
    return None


def _load(p: str | None) -> dict:
    if not p:
        return {"metrics": {}}
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _load_segmentation(seg_path: str | None) -> dict | None:
    """Lê o _segmentation do intermediate segmentado, se fornecido."""
    if not seg_path:
        return None
    try:
        return json.loads(Path(seg_path).read_text(encoding="utf-8")).get("_segmentation")
    except (OSError, json.JSONDecodeError):
        return None


def _input_hash(det: dict, trend: dict) -> str:
    basis = json.dumps(
        {"det": det.get("metrics"), "trend": trend.get("metrics"),
         "period": det.get("period"), "scope": det.get("scope")},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description="Congela métricas num snapshot rotulado")
    ap.add_argument("--label", required=True)
    ap.add_argument("--deterministic", required=True)
    ap.add_argument("--trend", required=True)
    ap.add_argument("--semantic", default=None)
    ap.add_argument("--segmented", default=None,
                    help="intermediate.segmented.json p/ registrar stats de segmentação")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    det = _load(args.deterministic)
    trend = _load(args.trend)
    sem = _load(args.semantic)
    segmentation = _load_segmentation(args.segmented)

    merged = {}
    merged.update(det.get("metrics", {}))
    merged.update(trend.get("metrics", {}))
    merged.update(sem.get("metrics", {}))

    # fórmula das derivadas (para validar comparação depois)
    formula = None
    re_metric = merged.get("resolution_efficiency", {})
    if re_metric:
        formula = (re_metric.get("detail") or {}).get("formula")

    task_count = det.get("taskCount") if det.get("taskCount") is not None else trend.get("taskCount")

    def _merge_group(det_g: dict, trend_g: dict) -> dict:
        out = {}
        for k in set(det_g) | set(trend_g):
            m = {}
            m.update((det_g.get(k) or {}).get("metrics", {}))
            m.update((trend_g.get(k) or {}).get("metrics", {}))
            out[k] = {
                "taskCount": (det_g.get(k) or {}).get("taskCount")
                or (trend_g.get(k) or {}).get("taskCount"),
                "metrics": m,
            }
        return out

    by_repo = _merge_group(det.get("byRepo") or {}, trend.get("byRepo") or {})
    by_mode = _merge_group(det.get("byMode") or {}, trend.get("byMode") or {})

    payload = {
        "_type": "harness-metrics-snapshot",
        "label": args.label,
        "skillVersion": SKILL_VERSION,
        "kiroVersion": _detect_kiro_version() or "unknown",
        # schemaVersion do log (registrado, mas NÃO usado para validar — ver docstring)
        "schemaVersion": (det.get("scope") or {}).get("schemaVersion"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "period": det.get("period") or trend.get("period"),
        "scope": det.get("scope") or trend.get("scope"),
        "taskCount": task_count,
        "inputHash": _input_hash(det, trend),
        "derivedFormula": {"resolution_efficiency": formula},
        "semanticEnabled": bool(sem.get("enabled")),
        "segmentation": segmentation,  # strategy, grayBoundaries, tieBreaker, llmRefined
        "unmappedActionTypes": det.get("unmappedActionTypes"),
        "metrics": merged,
        "byRepo": by_repo,
        "byMode": by_mode,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    unm = payload.get("unmappedActionTypes") or {}
    warn = ""
    if unm.get("ratio", 0) >= 0.2:
        warn = f" ⚠ {unm['ratio']*100:.0f}% actionTypes não mapeados (vocabulário mudou?)"
    print(f"[snapshot] label={args.label} tasks={task_count} kiro={payload['kiroVersion']} "
          f"→ {out}{warn}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
