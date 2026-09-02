#!/usr/bin/env python3
"""actions.py — classificação de actionType resiliente a mudança de vocabulário.

Contexto (ver review do PR #25): o Kiro renomeou os `actionType` de camelCase
(`readFiles`, `runCommand`) para snake_case (`read_files`, `run_command`) por volta
do 1.0.0, MAS manteve `schemaVersion: "1.0.0"` nos dois lados da virada. Sets fixos
num só vocabulário deixam de fora ~80% dos tool_calls e chegam a INVERTER o veredito
de Context Discovery Effort.

Este módulo é a fonte única da classificação. Trata os dois vocabulários como aliases
e normaliza tudo por uma chave canônica. `classify_action` devolve uma categoria; o que
não casar cai num fallback por verbo (cobre MCP e ferramentas novas). Só o que nem o
verbo reconhece vira "unknown", contabilizado por `unmapped_summary` para virar canário
no snapshot (avisa quando o vocabulário mudou de novo).
"""
from __future__ import annotations

import json
import re

# categorias canônicas
DISCOVERY = "discovery"      # ler/buscar contexto
IMPLEMENTATION = "impl"      # escrever/editar/apagar
OTHER = "other"              # ação conhecida mas neutra p/ o ratio (ex: hook, session update)
UNKNOWN = "unknown"          # actionType não reconhecido — alimenta o canário

# aliases: cada categoria mapeia os nomes conhecidos nos DOIS vocabulários (camel+snake)
# e variações observadas em IDE e CLI. Comparação é case-insensitive e normalizada.
_DISCOVERY_ALIASES = {
    "readfiles", "read_files", "readfile", "read_file", "read",
    "readcode", "read_code",
    "listdirectory", "list_directory",
    "filesearch", "file_search",
    "grepsearch", "grep_search", "search", "grep",
    "remotewebsearch", "remote_web_search", "websearch", "web_search",
    "webfetch", "web_fetch", "fetch",
    "mcp",
    "getdiagnostics", "get_diagnostics",
    # observação de processos em background (leitura)
    "getprocessoutput", "get_process_output", "listprocesses", "list_processes",
}
_IMPL_ALIASES = {
    "write", "fswrite", "fs_write",
    "replace", "strreplace", "str_replace", "edit",
    "create", "createfile", "create_file",
    "delete", "deletefile", "delete_file", "remove",
    "append", "fsappend", "fs_append",
    "semanticrename", "semantic_rename", "rename",
    "smartrelocate", "smart_relocate", "move",
}
# ações que existem mas não devem contar no ratio descoberta:implementação
_OTHER_ALIASES = {
    "createhook", "create_hook",
    "updatesessioninformation", "update_session_information",
    "todolist", "todo_list",
    "disclosecontext", "disclose_context",
    # controle de processos em background (start/stop) — ação, mas não impl. de código
    "controlprocess", "control_process",
}
# comando de shell é classificado pelo conteúdo (leitura vs mutação)
_RUN_ALIASES = {"runcommand", "run_command", "executebash", "execute_bash", "shell", "bash"}

# comandos de shell tipicamente de LEITURA (descoberta). Demais shells contam como "other"
# (não como implementação) para não inflar o denominador com git/npm/etc.
_READ_CMD_RE = re.compile(
    r"^\s*(cat|less|head|tail|ls|find|grep|rg|ag|wc|stat|tree|pwd|which|echo|"
    r"git\s+(status|log|diff|show|branch|remote)|cd|env|printenv)\b"
)

# Fallback por VERBO para ferramentas não listadas explicitamente (ex: MCP servers,
# que têm nomes arbitrários como "mcp_github_get_file_contents"). Em vez de virar
# UNKNOWN e escapar do ratio, classificamos pelo verbo do nome:
#   - verbo de leitura (get/read/list/search/fetch/...) → descoberta
#   - verbo de mutação (create/update/write/delete/push/merge/add/...) → other
# NÃO classificamos essas ferramentas como IMPLEMENTATION: não são edição de arquivo
# local do repo, então não devem inflar o denominador de Context Discovery Effort.
_READ_VERB_RE = re.compile(
    r"(^|_)(get|read|list|search|fetch|find|view|show|describe|query)(_|$|[A-Z])"
)
_WRITE_VERB_RE = re.compile(
    r"(^|_)(create|update|write|delete|remove|push|merge|add|reply|comment|set|move|rename|assign|transition)(_|$|[A-Z])"
)


def _verb_fallback(raw_name) -> str | None:
    """Classifica por verbo do nome quando não há alias explícito.

    Recebe o actionType ORIGINAL (não normalizado) para preservar limites de palavra.
    Retorna DISCOVERY / OTHER, ou None se o verbo não for reconhecível.
    """
    n = str(raw_name or "")
    if _READ_VERB_RE.search(n):
        return DISCOVERY
    if _WRITE_VERB_RE.search(n):
        return OTHER
    return None


def _norm(name) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _command_of(payload: dict) -> str:
    args = payload.get("args")
    if isinstance(args, str):
        try:
            return json.loads(args).get("command", "") or ""
        except (json.JSONDecodeError, AttributeError):
            return args
    if isinstance(args, dict):
        return args.get("command", "") or ""
    return ""


def classify_action(payload: dict) -> str:
    """Classifica um tool_call em DISCOVERY / IMPLEMENTATION / OTHER / UNKNOWN.

    Resiliente a camelCase e snake_case. Shell é decidido pelo comando; ferramentas
    sem alias explícito caem no fallback por verbo antes de virar UNKNOWN.
    """
    key = _norm(payload.get("actionType"))
    if not key:
        return UNKNOWN
    if key in _DISCOVERY_ALIASES:
        return DISCOVERY
    if key in _IMPL_ALIASES:
        return IMPLEMENTATION
    if key in _OTHER_ALIASES:
        return OTHER
    if key in _RUN_ALIASES:
        cmd = _command_of(payload)
        return DISCOVERY if _READ_CMD_RE.match(cmd or "") else OTHER
    # fallback por verbo (cobre MCP e ferramentas novas sem alias explícito)
    by_verb = _verb_fallback(payload.get("actionType"))
    if by_verb is not None:
        return by_verb
    return UNKNOWN


def is_discovery(payload: dict) -> bool:
    return classify_action(payload) == DISCOVERY


def is_implementation(payload: dict) -> bool:
    return classify_action(payload) == IMPLEMENTATION


def unmapped_summary(sessions: list) -> dict:
    """Canário: conta actionTypes não reconhecidos entre todos os tool_calls.

    Retorna {total, unmapped, ratio, byType} para o snapshot avisar quando o
    vocabulário do Kiro mudou e a classificação virou ruído.
    """
    total = 0
    unmapped = 0
    by_type: dict[str, int] = {}
    for s in sessions:
        for e in s.get("events", []):
            if e.get("type") != "tool_call":
                continue
            total += 1
            p = e.get("payload", {}) or {}
            if classify_action(p) == UNKNOWN:
                unmapped += 1
                at = str(p.get("actionType"))
                by_type[at] = by_type.get(at, 0) + 1
    top = dict(sorted(by_type.items(), key=lambda kv: -kv[1])[:10])
    return {
        "total": total,
        "unmapped": unmapped,
        "ratio": round(unmapped / total, 4) if total else 0.0,
        "byType": top,
    }
