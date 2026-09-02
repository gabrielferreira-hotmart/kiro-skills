#!/usr/bin/env python3
"""segment.py — infere fronteiras de "tarefa" via SCORE MULTI-SINAL.

Ver references/task-segmentation.md.

Em vez de uma regra binária baseada em regex (que mede o vocabulário do dev, não o
comportamento do Kiro), cada prompt de usuário recebe um "boundary score" que combina
vários sinais — a maioria comportamental e determinística:

  s1  gap temporal          resposta anterior → prompt atual (gap grande = tarefa nova)
  s2  troca de arquivos     arquivos tocados mudam completamente (disjunto = tarefa nova)
  s3  stopReason            turno anterior fechou em end_turn (entrega concluída)
  s4  recomeço c/ descoberta próximo bloco volta a ler/buscar do zero (readFiles/search)
  s5  sinal textual         regex de correção/follow-up — VOTO FRACO, não decide sozinho

score alto  → tarefa nova   (confidence high)
score baixo → continuação   (confidence high)
zona cinza  → confidence low; opcionalmente desempatada por LLM (segment_llm, opt-in)

Determinístico por padrão. O texto entra como um voto de baixo peso, então o estilo de
comunicação do dev deixa de dominar a decisão.

Entrada: intermediate.json (collect.py)
Saída:   mesmo JSON + por sessão "tasks" e "_segmentation" com contagem de fronteiras
         determinísticas vs cinzas.

Uso:
    python3 segment.py --in intermediate.json --out intermediate.segmented.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from actions import classify_action, DISCOVERY, IMPLEMENTATION
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from actions import classify_action, DISCOVERY, IMPLEMENTATION

# --- sinal textual (voto FRACO) ----------------------------------------------
CONTINUATION_PATTERNS = re.compile(
    r"\b(não é isso|nao e isso|volt[ae]|revert|desfaz|refaz|refaça|de novo|novamente|"
    r"corrig|ajust|arrum|conserta|na verdade|aliás|alias|"
    r"that's not|thats not|undo|redo|again|fix that|not what)\b",
    re.IGNORECASE,
)
FOLLOWUP_PATTERNS = re.compile(
    r"^\s*(sim\b|não\b|nao\b|ok\b|pode\b|isso\b|gosto\b|perfeito\b|certo\b|beleza\b|"
    r"e\s|mas\s|então\s|entao\s|agora\s|também\s|tambem\s|como\s|qual\s|quais\s|"
    r"por que\s|porque\s|e se\s|acrescent|adicion|coloca|inclui|"
    r"yes\b|no\b|and\s|but\s|also\s|now\s|what\s|how\s|why\s|add\s)",
    re.IGNORECASE,
)

# --- pesos e limiares do score -----------------------------------------------
# score > NEW_TASK_HI  → tarefa nova (alta confiança)
# score < CONT_LO      → continuação (alta confiança)
# entre os dois        → zona cinza (confidence low)
W_GAP = 0.35
W_FILES = 0.25
W_STOP = 0.15
W_DISCOVERY = 0.15
W_TEXT = 0.10  # voto fraco

NEW_TASK_HI = 0.60
CONT_LO = 0.35
CONTINUATION_GAP_SECONDS = 20 * 60
STRONG_GAP_SECONDS = 60 * 60  # gap > 1h praticamente garante tarefa nova

# classificação de descoberta/implementação vem de actions.py (resiliente a
# camelCase/snake_case — ver review do PR #25).


def _user_text(payload: dict) -> str:
    c = payload.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = [b.get("text") or b.get("data") or "" for b in c if isinstance(b, dict)]
        return " ".join(p for p in parts if isinstance(p, str))
    return ""


def _parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _files_in_block(events: list[dict], start: int, end: int) -> set[str]:
    files = set()
    for e in events[start : end + 1]:
        p = e.get("payload", {})
        if e.get("type") == "tool_call" and classify_action(p) == IMPLEMENTATION:
            fp = p.get("filePath")
            if fp:
                files.add(fp)
    return files


def _first_action_is_discovery(events: list[dict], start: int) -> bool:
    """A partir de start, a primeira tool_call é de descoberta?"""
    for e in events[start:]:
        if e.get("type") == "tool_call":
            return classify_action(e.get("payload", {})) == DISCOVERY
        if e.get("type") == "user" and e is not events[start]:
            break
    return False


def _text_vote(text: str) -> float:
    """Voto textual FRACO: 0 (continuação) .. 1 (tarefa nova)."""
    t = text.strip()
    if len(t) <= 25:
        return 0.0  # prompt curto → continuação
    if CONTINUATION_PATTERNS.search(t) or FOLLOWUP_PATTERNS.search(t):
        return 0.0
    return 0.6  # texto "neutro/longo" pende levemente pra tarefa nova


def _boundary_score(
    text: str,
    gap_seconds: float | None,
    prev_had_pending: bool,
    stop_end_turn: bool,
    files_prev: set[str],
    files_next: set[str],
    next_starts_discovery: bool,
) -> tuple[float, dict]:
    """Retorna (score, breakdown). score alto ⇒ tarefa nova."""
    # resposta a uma interação pendente nunca abre tarefa
    if prev_had_pending:
        return 0.0, {"reason": "post-pending_interaction"}

    # s1 gap temporal
    if gap_seconds is None:
        s_gap = 0.5
    elif gap_seconds >= STRONG_GAP_SECONDS:
        s_gap = 1.0
    elif gap_seconds <= CONTINUATION_GAP_SECONDS:
        s_gap = 0.0
    else:
        # interpola entre os dois limiares
        s_gap = (gap_seconds - CONTINUATION_GAP_SECONDS) / (
            STRONG_GAP_SECONDS - CONTINUATION_GAP_SECONDS
        )

    # s2 troca de arquivos (disjunto ⇒ tarefa nova; sobreposição ⇒ continuação)
    if not files_prev or not files_next:
        s_files = 0.5
    else:
        overlap = len(files_prev & files_next) / len(files_prev | files_next)
        s_files = 1.0 - overlap

    # s3 stopReason: turno anterior fechou entrega
    s_stop = 1.0 if stop_end_turn else 0.3

    # s4 recomeço com descoberta
    s_disc = 1.0 if next_starts_discovery else 0.2

    # s5 texto (voto fraco)
    s_text = _text_vote(text)

    score = (
        W_GAP * s_gap
        + W_FILES * s_files
        + W_STOP * s_stop
        + W_DISCOVERY * s_disc
        + W_TEXT * s_text
    )
    return score, {
        "gap": round(s_gap, 2),
        "files": round(s_files, 2),
        "stop": round(s_stop, 2),
        "discovery": round(s_disc, 2),
        "text": round(s_text, 2),
        "score": round(score, 3),
    }


def _segment_session(events: list[dict]) -> tuple[list[dict], dict]:
    tasks: list[dict] = []
    current: dict | None = None
    prev_pending = False
    prev_nonuser_ts = None
    prev_stop_end_turn = False
    prev_hard_boundary = False  # ex: /clear no CLI força nova tarefa
    gray_count = 0

    # pré-mapeia índices dos prompts de usuário para calcular blocos de arquivos
    user_indices = [i for i, e in enumerate(events) if e.get("type") == "user"]

    def _block_bounds(uidx: int) -> tuple[int, int]:
        # do prompt uidx até o próximo prompt (exclusivo) ou fim
        nxt = next((j for j in user_indices if j > uidx), len(events))
        return uidx, nxt - 1

    def close(end_idx: int, end_ts):
        if current is not None:
            current["endIdx"] = end_idx
            current["endTs"] = end_ts
            tasks.append(current)

    for idx, e in enumerate(events):
        etype = e.get("type")
        ts = e.get("timestamp")

        if etype == "user":
            text = _user_text(e.get("payload", {}))
            cur_dt, prev_dt = _parse_ts(ts), _parse_ts(prev_nonuser_ts)
            gap = (cur_dt - prev_dt).total_seconds() if cur_dt and prev_dt else None

            # arquivos do bloco anterior (tarefa corrente) vs do próximo bloco
            files_prev = set()
            if current is not None:
                files_prev = _files_in_block(events, current["startIdx"], idx - 1)
            b_start, b_end = _block_bounds(idx)
            files_next = _files_in_block(events, b_start, b_end)
            next_disc = _first_action_is_discovery(events, idx + 1)

            score, breakdown = _boundary_score(
                text, gap, prev_pending, prev_stop_end_turn,
                files_prev, files_next, next_disc,
            )

            if prev_hard_boundary:
                # /clear (CLI) ou evento equivalente: fronteira determinística
                opening, conf = True, "high"
                breakdown["hardBoundary"] = True
            elif score >= NEW_TASK_HI:
                opening, conf = True, "high"
            elif score <= CONT_LO:
                opening, conf = False, "high"
            else:
                # zona cinza: default conservador = continuação, mas marca low p/ tie-break
                opening, conf = (score >= (NEW_TASK_HI + CONT_LO) / 2), "low"
                gray_count += 1

            is_session_open = current is None
            if opening or is_session_open:
                close(idx - 1, events[idx - 1].get("timestamp") if idx > 0 else ts)
                # A 1ª tarefa da sessão é, por definição, o começo de uma tarefa:
                # marcamos confidence "high" (não "low"). Forçar "low" aqui inflava o
                # lowConfidenceCount e mandava o tie-breaker LLM desempatar aberturas
                # de sessão, onde não há prompt anterior para comparar (review PR #25).
                task_conf = "high" if is_session_open else conf
                current = {
                    "taskId": len(tasks) + 1,
                    "startIdx": idx,
                    "startTs": ts,
                    "endIdx": idx,
                    "endTs": ts,
                    "turnCount": 0,
                    "userMsgCount": 1,
                    "confidence": task_conf,
                    "sessionOpen": is_session_open,
                    "boundary": breakdown,
                    "openingPrompt": (text[:120] + "…") if len(text) > 120 else text,
                }
            else:
                current["userMsgCount"] += 1
            prev_pending = False
            prev_stop_end_turn = False
            prev_hard_boundary = False
        else:
            if etype == "turn_end":
                if current is not None:
                    current["turnCount"] += 1
                prev_stop_end_turn = e.get("payload", {}).get("stopReason") == "end_turn"
            if etype == "pending_interaction":
                prev_pending = True
            if etype == "session_event" and e.get("payload", {}).get("hardBoundary"):
                prev_hard_boundary = True
            if ts:
                prev_nonuser_ts = ts

    close(len(events) - 1, events[-1].get("timestamp") if events else None)
    return tasks, {"grayBoundaries": gray_count}


def segment(data: dict) -> dict:
    total_tasks = 0
    low_conf = 0
    gray = 0
    for session in data.get("sessions", []):
        tasks, info = _segment_session(session.get("events", []))
        session["tasks"] = tasks
        total_tasks += len(tasks)
        low_conf += sum(1 for t in tasks if t["confidence"] == "low")
        gray += info["grayBoundaries"]
    data["_segmentation"] = {
        "version": "1.0.0",
        "implemented": True,
        "strategy": "multi-signal-boundary-score",
        "signals": ["gap", "files", "stopReason", "discovery", "text(weak)", "hardBoundary"],
        "taskCount": total_tasks,
        "lowConfidenceCount": low_conf,
        "grayBoundaries": gray,
        "tieBreaker": "none",  # atualizado por segment_llm se rodar
    }
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Segmenta tarefas via score multi-sinal")
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.in_path).read_text(encoding="utf-8"))
    data = segment(data)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    seg = data["_segmentation"]
    print(
        f"[segment] {seg['taskCount']} tarefas | {seg['lowConfidenceCount']} baixa conf | "
        f"{seg['grayBoundaries']} fronteiras cinzas (candidatas a tie-break LLM)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
