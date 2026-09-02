#!/usr/bin/env python3
"""anonymize.py — remove/ofusca dados sensíveis antes de qualquer saída.

Ver references/privacy.md.

Aplica recursivamente sobre um JSON de métricas/intermediate:
  - sessionId → hash curto estável (permite drill-down sem expor id real)
  - paths absolutos → basename (remove estrutura de diretórios do usuário)
  - CHAVES de byRepo (paths absolutos) → basename também
  - segredos (AWS key, Bearer, PEM, gh token) → [REDACTED]
  - trechos de evidência (openingPrompt/example/...) → truncados a EVIDENCE_MAX

Uso:
    python3 anonymize.py --in metrics.json --out metrics.anon.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

EVIDENCE_MAX = 200
HOME = os.path.expanduser("~")

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"-----BEGIN [A-Z ]*KEY-----.*?-----END [A-Z ]*KEY-----", re.DOTALL),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),  # github tokens
]

# campos cujo valor é trecho de evidência a truncar
EVIDENCE_KEYS = {"openingPrompt", "evidence", "snippet", "example"}
# campos que contêm paths a reduzir para basename
PATH_KEYS = {"filePath", "workspacePaths", "local", "modified"}
# dicionários cujas CHAVES são paths absolutos (byRepo) → chave vira basename.
# byMode tem chave inócua (vibe/spec/cli), não precisa reduzir.
PATH_KEYED_DICTS = {"byRepo"}


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def redact_secrets(text: str) -> str:
    for pat in SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def strip_home(text: str) -> str:
    # remove o home dir do usuário de qualquer path que sobrou em texto livre
    return text.replace(HOME, "~")


def _clean_str(s: str, is_evidence: bool = False) -> str:
    s = redact_secrets(strip_home(s))
    if is_evidence and len(s) > EVIDENCE_MAX:
        s = s[:EVIDENCE_MAX] + "…"
    return s


def _reduce_path_key(k: str) -> str:
    """Reduz uma CHAVE que é path absoluto para basename, redigindo segredos/home."""
    base = os.path.basename(str(k).rstrip("/")) or str(k)
    return _clean_str(base)


def _walk(obj, key: str | None = None):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if key in PATH_KEYED_DICTS and isinstance(k, str):
                # dicionário indexado por path (byRepo): reduz a própria chave
                out[_reduce_path_key(k)] = _walk(v, k)
            elif k == "sessionId" and isinstance(v, str):
                out[k] = short_hash(v)
            elif k in PATH_KEYS:
                out[k] = _reduce_path(v)
            else:
                out[k] = _walk(v, k)
        return out
    if isinstance(obj, list):
        return [_walk(x, key) for x in obj]
    if isinstance(obj, str):
        return _clean_str(obj, is_evidence=(key in EVIDENCE_KEYS))
    return obj


def _reduce_path(v):
    if isinstance(v, str):
        return os.path.basename(v.rstrip("/")) or v
    if isinstance(v, list):
        return [_reduce_path(x) for x in v]
    return v


def anonymize(data: dict) -> dict:
    cleaned = _walk(data)
    if isinstance(cleaned, dict):
        cleaned["_anonymized"] = {"version": "1.0.0", "evidenceMaxChars": EVIDENCE_MAX}
    return cleaned


def main() -> int:
    ap = argparse.ArgumentParser(description="Anonimiza dados sensíveis")
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.in_path).read_text(encoding="utf-8"))
    data = anonymize(data)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[anonymize] hash de sessionId, redação de segredos e paths aplicados", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
