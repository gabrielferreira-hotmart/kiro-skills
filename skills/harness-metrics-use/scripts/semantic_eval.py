#!/usr/bin/env python3
"""semantic_eval.py — judge semântico via LLM EXTERNO (🟡).

STATUS: stub v0.1 — OFF por padrão. Só executa com --enable-llm-judge.

⚠️ PRIVACIDADE: ativar isto envia conversa e/ou trechos de código para um modelo
externo — exfiltração de dados potencialmente proprietários. Ver references/privacy.md.

Regras (ver privacy.md):
  - OFF por padrão; exige flag explícita --enable-llm-judge.
  - Usar modelo DIFERENTE do que gerou as sessões (reduz viés de auto-justificação).
  - Enviar o mínimo necessário (o trecho em avaliação, não a sessão inteira).
  - Resultado é ESTIMATIVA (class: trend), com citação da evidência (turno + toolCallId).

Uso:
    python3 semantic_eval.py --in intermediate.segmented.json \
        --out metrics.semantic.json --enable-llm-judge
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Judge semântico via LLM externo (opt-in)")
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--enable-llm-judge",
        action="store_true",
        help="OBRIGATÓRIO: confirma envio de dados a LLM externo (ver privacy.md)",
    )
    args = ap.parse_args()

    if not args.enable_llm_judge:
        print(
            "[semantic_eval] desativado (padrão). Rode com --enable-llm-judge para ativar "
            "o judge externo — isso ENVIA dados a um modelo externo. Ver references/privacy.md.",
            file=sys.stderr,
        )
        # saída vazia mas válida, para o pipeline seguir sem quebrar
        Path(args.out).write_text(
            json.dumps({"_type": "harness-metrics-semantic", "enabled": False, "metrics": {}},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 0

    # TODO(v0.2): implementar chamada ao LLM externo com rubric fixa + citação de evidência
    print("[semantic_eval] stub v0.1 — judge habilitado, implementação pendente", file=sys.stderr)
    Path(args.out).write_text(
        json.dumps({"_type": "harness-metrics-semantic", "enabled": True, "metrics": {}},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
