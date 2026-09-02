#!/usr/bin/env python3
"""collect.py — leitura somente-leitura do histórico de sessões do Kiro.

Lê ~/.kiro/sessions/<workspace-hash>/<session-uuid>/{session.json,messages.jsonl},
seleciona as sessões pelo período e (opcionalmente) por workspace, e normaliza os
eventos num intermediate.json consumido pelos scripts de métrica.

NUNCA modifica nada em ~/.kiro/. Só leitura.

Seleção por período (review PR #25):
    A sessão é SELECIONADA pelo período (createdAt/lastModifiedAt cruzam a janela) e,
    uma vez selecionada, TODOS os seus eventos entram. Antes filtrávamos evento a
    evento, o que truncava sessões que cruzavam a fronteira (turn_start sem turn_end,
    tarefa cortada). --to é inclusivo até o FIM do dia quando dado só-dia.

Escopo de workspace:
    - default: TODOS os workspaces (visão geral + quebra por repositório no report)
    - --workspace <path>: restringe a um workspace específico (opcional)

Origem (surface):
    - default: IDE + CLI (all). CLI tem limitações (sem timestamp por evento, sem
      contextUsage) e muitas sessões são de automação. Ver references/event-schema.md
      e references/baseline-after.md (migração v3 do CLI pode ter fidelidade diferente).

Sub-execuções:
    Eventos de sub-executions/*.jsonl (sub-agentes) são incorporados à sessão pai por
    padrão, para não subestimar Tool Failure Rate e Context Discovery Effort.

Uso:
    python3 collect.py --from 2026-08-01 --to 2026-08-31 \
        --out ./.harness-metrics/intermediate.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

# Aviso: o formato NÃO é documentado oficialmente e pode mudar entre versões do Kiro.
# schemaVersion se mostrou pouco confiável (ficou "1.0.0" antes e depois de uma quebra
# de vocabulário de actionType), então NÃO barramos por ele — apenas anotamos. Quem
# detecta a quebra de verdade é o canário unmappedActionTypes em metrics_deterministic.
SUPPORTED_SCHEMA_VERSIONS = {"1.0.0"}
SUPPORTED_DATA_MODEL_VERSIONS = {1}

SESSIONS_ROOT = Path.home() / ".kiro" / "sessions"


def _parse_date(s: str, *, is_end: bool = False) -> datetime:
    """Parse de data. Só-dia (YYYY-MM-DD) vira início do dia; se is_end, fim do dia.

    Datas só-dia são interpretadas em UTC (documentado); passe ISO 8601 com offset
    para controlar o fuso.
    """
    try:
        if len(s) == 10:
            d = datetime.fromisoformat(s).date()
            t = time(23, 59, 59, 999999) if is_end else time(0, 0, 0)
            return datetime.combine(d, t, tzinfo=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        print(f"[collect] data inválida: {s}", file=sys.stderr)
        raise SystemExit(2)


def _iter_ide_session_dirs(root: Path):
    """Gera o diretório de cada sessão de IDE (contém session.json + messages.jsonl)."""
    if not root.exists():
        print(f"[collect] diretório não encontrado: {root}", file=sys.stderr)
        return
    for workspace_dir in root.iterdir():
        if not workspace_dir.is_dir() or workspace_dir.name == "cli":
            continue
        for session_dir in workspace_dir.iterdir():
            if not session_dir.is_dir():
                continue
            if (session_dir / "session.json").exists() and (session_dir / "messages.jsonl").exists():
                yield session_dir


def _load_session_meta(session_json: Path) -> dict | None:
    try:
        meta = json.loads(session_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[collect] falha lendo {session_json}: {e}", file=sys.stderr)
        return None
    sv = str(meta.get("schemaVersion"))
    dmv = meta.get("dataModelVersion")
    if sv not in SUPPORTED_SCHEMA_VERSIONS or dmv not in SUPPORTED_DATA_MODEL_VERSIONS:
        meta["_schemaWarning"] = f"schema {sv}/{dmv} não validado por esta versão da skill"
    return meta


def _parse_ts(ts) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None


def _session_in_period(meta: dict, start: datetime, end: datetime) -> bool:
    """Seleciona a sessão se sua janela de atividade intersecta [start, end].

    Usa createdAt e lastModifiedAt. Se ambos ausentes, inclui (não dá para excluir
    com segurança).
    """
    created = _parse_ts(meta.get("createdAt"))
    modified = _parse_ts(meta.get("lastModifiedAt")) or created
    if created is None and modified is None:
        return True
    lo = created or modified
    hi = modified or created
    # intersecção de intervalos [lo,hi] com [start,end]
    return lo <= end and hi >= start


def _matches_workspace(meta: dict, workspace: str | None) -> bool:
    """True se a sessão pertence ao workspace pedido.

    workspace=None significa 'todos'. NOTA: a comparação casa nos dois sentidos
    (target é prefixo de rp OU rp é prefixo de target), então --workspace de um diretório
    pai puxa todos os subprojetos abaixo dele. Comportamento intencional (permite agrupar
    uma pasta de projetos), documentado aqui e no --help.
    """
    if workspace is None:
        return True
    target = os.path.realpath(workspace)
    paths = (meta.get("workspacePaths") or []) + (meta.get("rootPaths") or [])
    for p in paths:
        try:
            rp = os.path.realpath(p)
        except (OSError, ValueError):
            continue
        if rp == target or rp.startswith(target + os.sep) or target.startswith(rp + os.sep):
            return True
    return False


def _read_events(messages_path: Path) -> list[dict]:
    """Lê TODOS os eventos de um messages.jsonl (sem filtro por evento).

    A seleção já foi feita no nível da sessão; aqui levamos o log inteiro para não
    truncar tarefas que cruzam a fronteira do período.
    """
    events: list[dict] = []
    try:
        with messages_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = obj.get("payload", {}) or {}
                events.append({
                    "id": obj.get("id"),
                    "timestamp": obj.get("timestamp"),
                    "type": payload.get("type"),
                    "payload": payload,
                })
    except OSError as e:
        print(f"[collect] falha lendo {messages_path}: {e}", file=sys.stderr)
    return events


def _read_sub_executions(session_dir: Path) -> list[dict]:
    """Incorpora eventos de sub-executions/*.jsonl (sub-agentes) ao log da sessão.

    Mesmo shape de messages.jsonl. Sem isso, tool calls/falhas dos sub-agentes ficam
    invisíveis e subestimam Tool Failure Rate e Context Discovery Effort (review).
    """
    sub_dir = session_dir / "sub-executions"
    if not sub_dir.is_dir():
        return []
    extra: list[dict] = []
    for jf in sorted(sub_dir.glob("*.jsonl")):
        for e in _read_events(jf):
            e["_subExecution"] = True
            extra.append(e)
    return extra


def _collect_ide(start, end, workspace):
    """Coleta e normaliza sessões de IDE. Retorna (sessions, skipped_workspace)."""
    sessions_out = []
    skipped_workspace = 0
    for session_dir in _iter_ide_session_dirs(SESSIONS_ROOT):
        meta = _load_session_meta(session_dir / "session.json")
        if meta is None:
            continue
        if not _matches_workspace(meta, workspace):
            skipped_workspace += 1
            continue
        if not _session_in_period(meta, start, end):
            continue
        events = _read_events(session_dir / "messages.jsonl")
        events.extend(_read_sub_executions(session_dir))
        if not events:
            continue
        sessions_out.append({
            "sessionId": meta.get("id"),
            "surface": "ide",
            "agentMode": meta.get("agentMode"),
            "modelId": meta.get("modelId"),
            "status": meta.get("status"),
            "workspacePaths": meta.get("workspacePaths"),
            "createdAt": meta.get("createdAt"),
            "lastModifiedAt": meta.get("lastModifiedAt"),
            "schemaWarning": meta.get("_schemaWarning"),
            "eventCount": len(events),
            "events": events,
        })
    return sessions_out, skipped_workspace


def collect(from_date: str, to_date: str, workspace: str | None,
            surface: str = "all", include_automation: bool = False) -> dict:
    start = _parse_date(from_date)
    end = _parse_date(to_date, is_end=True)

    sessions_out: list[dict] = []
    skipped_workspace = 0

    if surface in ("ide", "all"):
        ide_sessions, skipped_workspace = _collect_ide(start, end, workspace)
        sessions_out.extend(ide_sessions)

    if surface in ("cli", "all"):
        try:
            from collectors_cli import iter_cli_sessions
        except ImportError:
            sys.path.insert(0, str(Path(__file__).parent))
            from collectors_cli import iter_cli_sessions
        for s in iter_cli_sessions(start, end, workspace, include_automation):
            sessions_out.append(s)

    by_surface: dict[str, int] = {}
    for s in sessions_out:
        by_surface[s.get("surface", "?")] = by_surface.get(s.get("surface", "?"), 0) + 1

    return {
        "_type": "harness-metrics-intermediate",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "period": {"from": from_date, "to": to_date,
                   "resolvedFrom": start.isoformat(), "resolvedTo": end.isoformat()},
        "scope": {
            "workspace": workspace or "ALL",
            "surface": surface,
            "skippedByWorkspace": skipped_workspace,
            "bySurface": by_surface,
        },
        "sessionCount": len(sessions_out),
        "sessions": sessions_out,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Coleta somente-leitura do histórico do Kiro")
    ap.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD ou ISO 8601")
    ap.add_argument("--to", dest="to_date", required=True,
                    help="YYYY-MM-DD (inclui o dia inteiro) ou ISO 8601")
    ap.add_argument("--out", required=True, help="caminho do intermediate.json de saída")
    ap.add_argument(
        "--workspace",
        default=None,
        help="OPCIONAL: restringe a um workspace. Casa também subdiretórios (um dir pai "
             "puxa os subprojetos). Por padrão analisa TODOS os workspaces.",
    )
    ap.add_argument(
        "--surface",
        choices=["ide", "cli", "all"],
        default="all",
        help="qual origem coletar: IDE, CLI ou ambas (default: all). CLI tem menos "
             "fidelidade (sem timestamp/contextUsage por evento).",
    )
    ap.add_argument(
        "--include-automation",
        action="store_true",
        help="inclui sessões CLI de automação (subagent/cron); por padrão são ignoradas",
    )
    args = ap.parse_args()

    result = collect(args.from_date, args.to_date, args.workspace,
                     surface=args.surface, include_automation=args.include_automation)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[collect] {result['sessionCount']} sessões {result['scope']['bySurface']} | "
        f"escopo={result['scope']['workspace']} | período {args.from_date}..{args.to_date} → {out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
