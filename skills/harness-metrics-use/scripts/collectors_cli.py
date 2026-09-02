#!/usr/bin/env python3
"""collectors_cli.py — adaptador do histórico do Kiro CLI para o modelo de eventos do IDE.

O CLI (~/.kiro/sessions/cli/<uuid>.{json,jsonl}) tem formato próprio, diferente do IDE.
Este módulo normaliza cada sessão CLI para o MESMO shape de eventos que collect.py produz
para o IDE, para que segment.py e as métricas funcionem sem saber a origem.

Diferenças do CLI (documentadas em event-schema.md):
  - eventos são {version, kind, data}; kind ∈ {Prompt, AssistantMessage, ToolResults, Clear}
  - NÃO há timestamp por evento (só created_at/updated_at na sessão) → gap temporal
    da segmentação fica indisponível; marcamos timestamp=None
  - NÃO há stopReason nem contextUsage
  - metadados ficam em <uuid>.json (session_id, cwd, session_created_reason)

Mapeamento kind → payload.type do IDE:
  Prompt           → user
  AssistantMessage → assistant (+ tool_call para cada bloco toolUse)
  ToolResults      → tool_result (por bloco toolResult; sucesso via exit_status)
  Clear            → session_event(hardBoundary) — /clear zera o contexto, fronteira dura

Filtro: sessões de automação (session_created_reason ∈ {subagent, cron}) são puladas
por padrão — não são uso interativo de dev. Controlado por include_automation.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

CLI_ROOT = Path.home() / ".kiro" / "sessions" / "cli"
AUTOMATION_REASONS = {"subagent", "cron", "hook", "heartbeat"}


def _text_from_content(content) -> str:
    """Extrai texto de uma lista de blocos {kind, data}."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("kind") == "text":
            d = b.get("data")
            if isinstance(d, str):
                parts.append(d)
    return "\n".join(parts)


def _tool_calls_from_assistant(content) -> list[dict]:
    """Extrai tool_calls dos blocos toolUse de uma AssistantMessage."""
    calls = []
    if not isinstance(content, list):
        return calls
    for b in content:
        if isinstance(b, dict) and b.get("kind") == "toolUse":
            d = b.get("data", {}) or {}
            name = d.get("name", "")
            inp = d.get("input", {}) or {}
            calls.append(
                {
                    "toolCallId": d.get("toolUseId"),
                    "toolName": name,
                    "actionType": _map_action(name, inp),
                    "args": json.dumps(inp, ensure_ascii=False),
                    "filePath": inp.get("path") or inp.get("filePath"),
                }
            )
    return calls


# mapeia nome de tool do CLI para o actionType usado pelas métricas do IDE.
# Preserva o nome original quando possível — actions.py já reconhece os dois
# vocabulários (camelCase e snake_case), então não precisamos forçar um formato.
# Corrige também o bug antigo de classificar qualquer "search" como web search.
def _map_action(name: str, inp: dict) -> str:
    n = (name or "").lower()
    if n in ("shell", "execute_bash", "executebash", "run_command", "runcommand"):
        return "run_command"
    if n in ("fs_read", "read_files", "readfile", "read"):
        return "read_files"
    if n in ("fs_write", "write", "create"):
        return "write"
    if n in ("str_replace", "replace", "edit"):
        return "replace"
    if n in ("delete", "delete_file"):
        return "delete"
    if "grep" in n or n in ("file_search", "grep_search"):
        return "grep_search"
    # busca na web é diferente de busca em código — não colapsar tudo em web search
    if "web" in n and "search" in n:
        return "web_search"
    if "search" in n:
        return "grep_search"
    # nome original: actions.py normaliza e classifica; se não reconhecer, vira canário
    return name or "unknown"


def _tool_results(content, results) -> list[dict]:
    """Normaliza blocos toolResult em tool_result do IDE (success + content)."""
    out = []
    blocks = content if isinstance(content, list) else []
    for b in blocks:
        if not (isinstance(b, dict) and b.get("kind") == "toolResult"):
            continue
        d = b.get("data", {}) or {}
        tool_id = d.get("toolUseId")
        inner = d.get("content", [])
        text, success = _flatten_tool_result(inner, d)
        out.append(
            {
                "toolCallId": tool_id,
                "content": text,
                "success": success,
                "durationMs": None,
            }
        )
    return out


def _flatten_tool_result(inner, data) -> tuple[str, bool]:
    """Extrai texto e sucesso de um toolResult. Sucesso vem do exit_status quando há."""
    text_parts = []
    success = True
    status = data.get("status")
    if status == "error":
        success = False
    items = inner if isinstance(inner, list) else []
    for it in items:
        if not isinstance(it, dict):
            continue
        d = it.get("data")
        if it.get("kind") == "json" and isinstance(d, dict):
            es = d.get("exit_status", "")
            if isinstance(es, str) and es and "status: 0" not in es:
                success = False
            for key in ("stdout", "stderr", "output"):
                v = d.get(key)
                if isinstance(v, str) and v:
                    text_parts.append(v)
        elif it.get("kind") == "text" and isinstance(d, str):
            text_parts.append(d)
    return ("\n".join(text_parts))[:4000], success


def _in_period(dt_str, start, end) -> bool:
    if not dt_str:
        return True  # sem timestamp de sessão: não dá pra filtrar, inclui
    try:
        t = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return True
    return start <= t <= end


def iter_cli_sessions(start, end, workspace, include_automation: bool = False):
    """Gera sessões CLI normalizadas no shape do collect.py (mesmos campos)."""
    if not CLI_ROOT.exists():
        return
    target = os.path.realpath(workspace) if workspace else None
    for meta_path in sorted(CLI_ROOT.glob("*.json")):
        jsonl_path = meta_path.with_suffix(".jsonl")
        if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        reason = meta.get("session_created_reason")
        if not include_automation and reason in AUTOMATION_REASONS:
            continue

        created = meta.get("created_at")
        updated = meta.get("updated_at")
        # filtro de período: usa updated_at se houver; senão inclui
        if not _in_period(updated or created, start, end):
            continue

        # filtro de workspace via cwd
        cwd = meta.get("cwd")
        if target and cwd:
            rp = os.path.realpath(cwd)
            if not (rp == target or rp.startswith(target + os.sep) or target.startswith(rp + os.sep)):
                continue

        events = _normalize_cli_events(jsonl_path, created)
        if not events:
            continue
        yield {
            "sessionId": meta.get("session_id"),
            "surface": "cli",
            "agentMode": "cli",
            "modelId": meta.get("model") or "cli",
            "status": None,
            "workspacePaths": [cwd] if cwd else [],
            "createdAt": created,
            "lastModifiedAt": updated,
            "sessionCreatedReason": reason,
            "schemaWarning": "CLI: sem timestamp por evento; gap temporal e contextUsage indisponíveis",
            "eventCount": len(events),
            "events": events,
        }


def _normalize_cli_events(jsonl_path: Path, session_created: str | None) -> list[dict]:
    """Converte as linhas {version,kind,data} do CLI em eventos no shape do IDE.

    Como o CLI não tem timestamp por evento, usamos None (segment.py trata gap=None
    como sinal neutro). Inserimos turn_start/turn_end sintéticos por Prompt para que
    a contagem de turnos funcione.
    """
    events: list[dict] = []
    open_turn = False

    def add(etype, payload):
        payload = dict(payload)
        payload["type"] = etype
        events.append({"id": None, "timestamp": None, "type": etype, "payload": payload})

    for line in jsonl_path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = o.get("kind")
        data = o.get("data", {}) or {}

        if kind == "Clear":
            # /clear zera o contexto do CLI — fronteira DURA de tarefa. Fecha o turno
            # aberto e marca para o segmentador forçar uma nova tarefa no próximo prompt.
            if open_turn:
                add("turn_end", {"stopReason": "end_turn"})
                open_turn = False
            add("session_event", {"event": "clear", "hardBoundary": True})
        elif kind == "Prompt":
            if open_turn:
                add("turn_end", {"stopReason": "end_turn"})
            add("user", {"content": _text_from_content(data.get("content")), "source": "cli"})
            add("turn_start", {})
            open_turn = True
        elif kind == "AssistantMessage":
            txt = _text_from_content(data.get("content"))
            if txt:
                add("assistant", {"content": txt, "operationType": "Say"})
            for tc in _tool_calls_from_assistant(data.get("content")):
                add("tool_call", tc)
        elif kind == "ToolResults":
            for tr in _tool_results(data.get("content"), data.get("results")):
                add("tool_result", tr)

    if open_turn:
        add("turn_end", {"stopReason": "end_turn"})
    return events
