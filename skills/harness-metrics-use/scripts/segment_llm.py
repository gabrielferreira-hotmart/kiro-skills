#!/usr/bin/env python3
"""segment_llm.py — tie-breaker semântico OPCIONAL para fronteiras de tarefa.

STATUS: OFF por padrão. Só executa com --enable-llm-judge.

Papel: refinar APENAS as fronteiras que a segmentação determinística (segment.py)
marcou como confidence="low" (zona cinza). Não reprocessa a sessão inteira.

⚠️ PRIVACIDADE (ver references/privacy.md):
  - opt-in explícito (--enable-llm-judge);
  - envia SÓ o par de mensagens da fronteira (prompt anterior encerrando + prompt novo),
    truncado — nunca a sessão inteira;
  - usar modelo DIFERENTE do que gerou as sessões (menos viés);
  - decisão da LLM ajusta o confidence para "high" e marca tieBreaker="llm".

Sem a flag: passthrough — devolve o input inalterado e marca tieBreaker="skipped".

Contrato do adaptador de LLM: implementar `classify_boundary(prev_text, next_text) -> bool`
(True = tarefa nova, False = continuação). Deixado como ponto de extensão para não
acoplar a skill a um provedor específico.

Uso:
    python3 segment_llm.py --in segmented.json --out segmented.llm.json --enable-llm-judge
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PREV_MAX = 300
NEXT_MAX = 300


def classify_boundary(prev_text: str, next_text: str) -> bool:
    """Ponto de extensão. Deve retornar True se `next_text` inicia uma tarefa NOVA.

    Implementação real deve chamar um LLM externo com rubric fixa, por exemplo:

        "Dadas duas mensagens consecutivas de um usuário a um assistente de código,
         a segunda inicia uma TAREFA NOVA (objetivo diferente) ou é CONTINUAÇÃO
         (follow-up, correção, refinamento) da primeira? Responda new|cont."

    Enviar apenas prev_text[:PREV_MAX] e next_text[:NEXT_MAX].
    NÃO implementado aqui (sem provedor acoplado); levanta erro se chamado.
    """
    raise NotImplementedError(
        "classify_boundary não implementado — acople um provedor de LLM externo aqui"
    )


def _opening_prompt_pairs(data: dict):
    """Gera (session, task) para cada tarefa com confidence low (fronteira cinza)."""
    for session in data.get("sessions", []):
        tasks = session.get("tasks", [])
        for i, t in enumerate(tasks):
            if t.get("confidence") == "low":
                prev = tasks[i - 1] if i > 0 else None
                yield session, tasks, i, prev, t


def refine(data: dict) -> dict:
    refined = 0
    errors = 0
    for session, tasks, i, prev, t in _opening_prompt_pairs(data):
        prev_text = (prev or {}).get("openingPrompt", "") if prev else ""
        next_text = t.get("openingPrompt", "")
        try:
            is_new = classify_boundary(prev_text[:PREV_MAX], next_text[:NEXT_MAX])
        except NotImplementedError:
            errors += 1
            continue
        t["confidence"] = "high"
        t["tieBreaker"] = "llm"
        t["_llmDecision"] = "new" if is_new else "cont"
        refined += 1
        # nota: fundir tarefas quando is_new=False exige recomputar índices; deixado
        # para a implementação real. Aqui apenas anotamos a decisão.
    seg = data.setdefault("_segmentation", {})
    seg["tieBreaker"] = "llm" if refined else "attempted-not-implemented"
    seg["llmRefined"] = refined
    seg["llmErrors"] = errors
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Tie-breaker LLM para fronteiras cinzas (opt-in)")
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--enable-llm-judge",
        action="store_true",
        help="OBRIGATÓRIO: confirma envio de trechos a LLM externo (ver privacy.md)",
    )
    args = ap.parse_args()

    data = json.loads(Path(args.in_path).read_text(encoding="utf-8"))

    if not args.enable_llm_judge:
        seg = data.setdefault("_segmentation", {})
        seg["tieBreaker"] = "skipped"
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            "[segment_llm] desativado (padrão). Segmentação determinística mantida. "
            "Rode com --enable-llm-judge para desempatar fronteiras cinzas (ENVIA dados "
            "a LLM externo — ver references/privacy.md).",
            file=sys.stderr,
        )
        return 0

    data = refine(data)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    seg = data.get("_segmentation", {})
    print(
        f"[segment_llm] tieBreaker={seg.get('tieBreaker')} refinadas={seg.get('llmRefined')} "
        f"erros={seg.get('llmErrors')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
