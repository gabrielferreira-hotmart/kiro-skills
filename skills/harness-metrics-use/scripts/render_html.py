#!/usr/bin/env python3
"""render_html.py — gera o dashboard HTML.

Modo PRINCIPAL: relatório de PERÍODO ÚNICO a partir de um snapshot (snapshot.py).
Modo secundário (opcional): comparação baseline → after a partir de um report.json
(compare.py), para quem quiser confrontar dois períodos.

O tipo é detectado pelo campo `_type` do arquivo de entrada:
  - harness-metrics-snapshot → relatório de período único (padrão)
  - harness-metrics-report   → comparação com Δ%

REGRA CENTRAL: lê o campo `class` de cada métrica e aplica o marcador:
  🟢 deterministic → "fato"
  🟡 trend         → "tendência (comparação relativa)"
A apresentação NUNCA decide a classe — só reflete o que o dado declara.

Seções: Overview | Quality | Efficiency | Consumption.
Sem dependências externas (HTML+CSS inline).

Uso:
    # período único (principal)
    python3 render_html.py --in snapshots/2026-08.json --out report-2026-08.html
    # comparação (opcional)
    python3 render_html.py --in report.json --out report.html
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# agrupamento das métricas em seções do dashboard
# Métricas agrupadas por CLASSE de confiança.
# Determinísticas (🟢) primeiro — são fato. Tendências (🟡) depois — indicadores.
DETERMINISTIC_ORDER = [
    "turns_to_resolution",
    "elapsed_seconds",
    "tool_failure_rate",
    "context_discovery_effort",
    "context_usage",
    "rework_rate",
    "hallucination_intrasession",
    "tool_rejection_rate",
    "aborted_turn_rate",
    "context_truncation",
    "credits_used",
]
TREND_ORDER = [
    "first_pass_resolution",
    "human_correction_rate",
    "hallucination_semantic",
]
# score agregado — seção própria, pois combina várias métricas em um índice
SUMMARY_ORDER = ["resolution_efficiency"]

LABELS = {
    "first_pass_resolution": "First Pass Resolution",
    "human_correction_rate": "Human Correction Rate",
    "hallucination_intrasession": "Hallucination Evidence (intra-sessão)",
    "hallucination_semantic": "Hallucination Evidence (semântica)",
    "rework_rate": "Rework Rate",
    "turns_to_resolution": "Turns to Resolution",
    "tool_failure_rate": "Tool Failure Rate",
    "context_discovery_effort": "Context Discovery Effort",
    "resolution_efficiency": "Resolution Efficiency",
    "context_usage": "Context Usage (%)",
    "tool_rejection_rate": "Tool Rejection Rate",
    "aborted_turn_rate": "Aborted Turn Rate",
    "credits_used": "Credits Used",
    "elapsed_seconds": "Execution Time",
    "context_truncation": "Context Truncation",
}

# descrição curta e didática do que cada métrica representa
DESCRIPTIONS = {
    "first_pass_resolution": "Quantas tarefas o Kiro resolveu na primeira tentativa, sem você precisar corrigir depois. Quanto maior, melhor.",
    "human_correction_rate": "Quantas vezes, em média por tarefa, você precisou corrigir o rumo do Kiro. Quanto menor, melhor.",
    "hallucination_intrasession": "Casos em que o Kiro afirmou que um arquivo/caminho existia e uma ferramenta o desmentiu na sequência. Evidência forte de alucinação. Quanto menor, melhor.",
    "hallucination_semantic": "Casos em que você corrigiu um fato que o Kiro tinha afirmado (ex: 'esse método não existe'). Sinal mais fraco, por texto. Quanto menor, melhor.",
    "rework_rate": "Retrabalho por tarefa: edições repetidas no mesmo arquivo e reversões. Quanto menor, melhor.",
    "turns_to_resolution": "Quantas idas e vindas (turnos) foram necessárias, em média, para concluir uma tarefa. Quanto menor, melhor.",
    "tool_failure_rate": "Fração de ferramentas/comandos que falharam de verdade (erros benignos já descontados). Quanto menor, melhor.",
    "context_discovery_effort": "Quanto o Kiro precisou explorar (ler/buscar) por cada ação de implementação. Alto = ele gasta muito esforço achando contexto antes de agir. Quanto menor, melhor.",
    "resolution_efficiency": "Índice-resumo de 0 a 1 que combina resultado (tarefas resolvidas de primeira) e esforço (turnos + correções). Perto de 1 = muito resultado com pouco esforço; perto de 0 = muito esforço para pouco resultado. É a leitura geral: quanto maior, melhor.",
    "context_usage": "Quanto da janela de contexto foi usada, em média. Só é preocupante quando fica muito alto (risco de perder contexto/compactar). Janela sobrando não é defeito.",
    "tool_rejection_rate": "Fração de ações propostas pelo Kiro que você rejeitou na aprovação. É correção humana determinística (você vetou antes de executar). Quanto menor, melhor.",
    "aborted_turn_rate": "Fração de turnos que terminaram cancelados/falhos/abortados. Sinal de que a execução estava indo pelo caminho errado. Quanto menor, melhor.",
    "credits_used": "Créditos somados a partir de promptTurnSummaries das sessões (quando o Kiro registra). Aproximação de custo — não validada contra a UI. Menor = mais barato para o mesmo trabalho.",
    "elapsed_seconds": "Tempo real de execução por turno (mediana), a partir de usage_summary.elapsedTime. Menor = respostas mais rápidas.",
    "context_truncation": "Quantas vezes o Kiro precisou sumarizar/truncar o contexto por sessão (evento tombstone). Muitas truncagens = sessões longas demais empurrando contexto para fora. Quanto menor, melhor.",
}

# faixas de avaliação por métrica: lista de (limite, veredito, cor, motivo).
# 'higher_better' define a direção. Avaliado em ordem; primeiro que casar vence.
# veredito ∈ {good, mid, bad}
EVAL_RANGES = {
    "first_pass_resolution": ("higher", [(0.80, "good"), (0.60, "mid"), (0.0, "bad")]),
    "human_correction_rate": ("lower", [(0.20, "good"), (0.50, "mid"), (9e9, "bad")]),
    # hallucination agora é TAXA por tarefa (não contagem absoluta)
    "hallucination_intrasession": ("lower", [(0.02, "good"), (0.10, "mid"), (9e9, "bad")]),
    "hallucination_semantic": ("lower", [(0.05, "good"), (0.15, "mid"), (9e9, "bad")]),
    "rework_rate": ("lower", [(0.5, "good"), (1.5, "mid"), (9e9, "bad")]),
    "turns_to_resolution": ("lower", [(4, "good"), (8, "mid"), (9e9, "bad")]),
    "tool_failure_rate": ("lower", [(0.05, "good"), (0.15, "mid"), (9e9, "bad")]),
    "context_discovery_effort": ("lower", [(1.0, "good"), (3.0, "mid"), (9e9, "bad")]),
    "resolution_efficiency": ("higher", [(0.65, "good"), (0.40, "mid"), (0.0, "bad")]),
    "tool_rejection_rate": ("lower", [(0.05, "good"), (0.20, "mid"), (9e9, "bad")]),
    "aborted_turn_rate": ("lower", [(0.10, "good"), (0.25, "mid"), (9e9, "bad")]),
    "context_truncation": ("lower", [(0.0, "good"), (1.0, "mid"), (9e9, "bad")]),
    # context_usage: só o TOPO é ruim. Janela sobrando (baixo) é saudável (review).
    "context_usage": ("cap", [(85,)]),
    # credits_used e elapsed_seconds não têm faixa universal de "bom/ruim" —
    # só fazem sentido comparados entre períodos. Ficam sem veredito (na).
}

VERDICT_LABEL = {"good": "Bom", "mid": "Médio", "bad": "Ruim", "na": "—"}
VERDICT_WHY = {
    "first_pass_resolution": {
        "good": "a maioria das tarefas saiu certa de primeira.",
        "mid": "boa parte exigiu correção depois da primeira entrega.",
        "bad": "muitas tarefas precisaram ser refeitas após a primeira tentativa.",
    },
    "human_correction_rate": {
        "good": "você raramente precisou corrigir o rumo.",
        "mid": "correções aconteceram com alguma frequência.",
        "bad": "você teve que corrigir o Kiro com muita frequência.",
    },
    "hallucination_intrasession": {
        "good": "nenhuma (ou quase nenhuma) afirmação foi desmentida por ferramenta.",
        "mid": "houve alguns casos de afirmação contradita por ferramenta.",
        "bad": "muitas afirmações do Kiro foram desmentidas na sequência.",
    },
    "hallucination_semantic": {
        "good": "você quase não precisou corrigir fatos afirmados pelo Kiro.",
        "mid": "houve algumas correções factuais suas.",
        "bad": "você corrigiu fatos do Kiro com frequência.",
    },
    "rework_rate": {
        "good": "pouco retrabalho — as implementações raramente foram refeitas.",
        "mid": "algum retrabalho sobre o mesmo código.",
        "bad": "muito retrabalho: o mesmo código foi mexido/revertido várias vezes.",
    },
    "turns_to_resolution": {
        "good": "as tarefas fecharam em poucas idas e vindas.",
        "mid": "as tarefas exigiram um número moderado de turnos.",
        "bad": "as tarefas precisaram de muitos turnos até concluir.",
    },
    "tool_failure_rate": {
        "good": "quase todas as ferramentas/comandos rodaram sem erro real.",
        "mid": "uma parcela relevante de comandos falhou.",
        "bad": "muitos comandos falharam de verdade.",
    },
    "context_discovery_effort": {
        "good": "o Kiro achou o contexto rápido e partiu para a implementação.",
        "mid": "gastou um esforço moderado explorando antes de agir.",
        "bad": "gastou muito esforço explorando para cada ação — sinal de contexto mal disponível.",
    },
    "resolution_efficiency": {
        "good": "bom resultado com pouco esforço.",
        "mid": "resultado razoável, mas com esforço considerável.",
        "bad": "muito esforço para o resultado entregue.",
    },
    "tool_rejection_rate": {
        "good": "você quase não precisou vetar ações propostas.",
        "mid": "vetou uma parcela relevante das ações propostas.",
        "bad": "vetou muitas ações — o Kiro propôs bastante coisa fora do esperado.",
    },
    "aborted_turn_rate": {
        "good": "quase nenhum turno foi cancelado/abortado.",
        "mid": "alguns turnos terminaram cancelados ou com falha.",
        "bad": "muitos turnos foram abortados — sinal de rumo errado com frequência.",
    },
    "context_truncation": {
        "good": "o contexto quase não precisou ser sumarizado.",
        "mid": "houve sumarização de contexto em algumas sessões.",
        "bad": "muita sumarização — sessões longas empurrando contexto para fora.",
    },
}


def _verdict(key, value):
    """Retorna (verdict, motivo) para o valor da métrica. verdict ∈ good|mid|bad|na."""
    if value is None:
        return "na", "sem dados suficientes no período."
    cfg = EVAL_RANGES.get(key)
    if not cfg:
        return "na", ""
    direction, ranges = cfg
    if direction == "band":
        lo, hi = ranges[0]
        if lo <= value <= hi:
            return "good", f"dentro da faixa saudável ({lo}–{hi}%)."
        if value > hi:
            return "bad", f"acima de {hi}% — risco de perder contexto/compactar."
        return "mid", f"abaixo de {lo}% — contexto pode estar subutilizado."
    if direction == "cap":
        # só o topo é ruim; abaixo do teto está tudo bem (janela sobrando é saudável)
        hi = ranges[0][0]
        if value >= hi:
            return "bad", f"acima de {hi}% — risco de perder contexto/compactar."
        if value >= hi - 15:
            return "mid", f"perto do teto ({hi}%) — de olho para não compactar."
        return "good", "dentro de uma faixa confortável de uso da janela."
    if direction == "higher":
        for limit, verdict in ranges:
            if value >= limit:
                return verdict, VERDICT_WHY.get(key, {}).get(verdict, "")
    else:  # lower is better
        for limit, verdict in ranges:
            if value <= limit:
                return verdict, VERDICT_WHY.get(key, {}).get(verdict, "")
    return "na", ""

STYLE = """
:root{--det:#137333;--detbg:#e6f4ea;--trend:#b06000;--trendbg:#fef7e0;--worse:#c5221f;--better:#137333}
*{box-sizing:border-box}
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,sans-serif;margin:0;background:#fafafa;color:#1f1f1f}
header{background:#1a1a2e;color:#fff;padding:1.5rem 2rem}
header h1{margin:0 0 .3rem;font-size:1.4rem}
header .sub{opacity:.8;font-size:.9rem}
main{max-width:960px;margin:0 auto;padding:1.5rem 2rem}
.legend{font-size:.85rem;color:#444;margin:.5rem 0 1.5rem}
.badge{padding:.1rem .45rem;border-radius:.35rem;font-size:.78rem;font-weight:600}
.badge.det{background:var(--detbg);color:var(--det)}
.badge.trend{background:var(--trendbg);color:var(--trend)}
.warn{background:#fce8e6;color:#8c1d18;padding:.5rem .8rem;border-radius:.4rem;margin:.4rem 0;font-size:.88rem}
section{background:#fff;border:1px solid #eaeaea;border-radius:.6rem;margin:1.2rem 0;overflow:hidden}
section h2{margin:0;padding:.8rem 1.2rem;background:#f5f5f7;font-size:1.05rem;border-bottom:1px solid #eaeaea}
.metric{display:grid;grid-template-columns:1.6rem 1fr auto;gap:.6rem;align-items:center;padding:.7rem 1.2rem;border-bottom:1px solid #f4f4f4}
.metric:last-child{border-bottom:none}
.mname{font-weight:500}
.mnote{font-size:.78rem;color:#777;display:block;margin-top:.15rem}
.mval{text-align:right;font-variant-numeric:tabular-nums}
.delta{font-size:.82rem;margin-left:.5rem;padding:.05rem .4rem;border-radius:.3rem}
.delta.better{background:var(--detbg);color:var(--better)}
.delta.worse{background:#fce8e6;color:var(--worse)}
.delta.flat,.delta\\.na{background:#eee;color:#666}
.n{font-size:.75rem;color:#999}
.mdesc{font-size:.8rem;color:#555;display:block;margin-top:.25rem;line-height:1.35}
.verdict{display:inline-block;font-size:.75rem;font-weight:600;padding:.08rem .45rem;border-radius:.3rem;margin-top:.3rem}
.verdict.good{background:var(--detbg);color:var(--better)}
.verdict.mid{background:#fef7e0;color:#b06000}
.verdict.bad{background:#fce8e6;color:var(--worse)}
.verdict.na{background:#eee;color:#666}
.vwhy{font-size:.78rem;color:#666;margin-left:.4rem;font-weight:400}
.example{font-size:.78rem;color:#444;background:#f7f7f9;border-left:3px solid #d0d0d8;padding:.35rem .6rem;margin-top:.4rem;border-radius:.2rem;line-height:1.4}
.example .lbl{color:#888;font-weight:600;text-transform:uppercase;font-size:.68rem;letter-spacing:.03em}
.sechint{font-size:.8rem;color:#666;font-weight:400;margin-left:.5rem}
.repotbl{width:100%;border-collapse:collapse;font-size:.85rem}
.repotbl th,.repotbl td{padding:.5rem .7rem;text-align:right;border-bottom:1px solid #f0f0f0}
.repotbl th{font-size:.72rem;text-transform:uppercase;letter-spacing:.03em;color:#888;font-weight:600}
.repotbl th:first-child,.repotbl td:first-child{text-align:left}
.repotbl td.repo{font-weight:600}
.repotbl .rtc{display:block;font-size:.72rem;color:#999;font-weight:400}
.rv{font-variant-numeric:tabular-nums;padding:.05rem .35rem;border-radius:.25rem}
.rv.good{background:var(--detbg);color:var(--better)}
.rv.mid{background:#fef7e0;color:#b06000}
.rv.bad{background:#fce8e6;color:var(--worse)}
.rv.na{color:#999}
.metric-single{display:grid;grid-template-columns:1.6rem 1fr 12rem;gap:.6rem;padding:.85rem 1.2rem;border-bottom:1px solid #f4f4f4}
.metric-single:last-child{border-bottom:none}
.metric-single .mval{align-self:start;text-align:right}
.metric-single .mnum{font-size:1.15rem;font-weight:700;line-height:1.2}
.metric-single .mexpl{font-size:.76rem;color:#666;margin-top:.15rem;line-height:1.3}
.overview{display:flex;gap:1rem;flex-wrap:wrap;padding:1rem 1.2rem}
.card{flex:1;min-width:140px;background:#f8f9fb;border-radius:.5rem;padding:.8rem}
.card .k{font-size:.78rem;color:#666}
.card .v{font-size:1.3rem;font-weight:600;margin-top:.2rem}
footer{max-width:960px;margin:0 auto;padding:1rem 2rem 2rem;color:#999;font-size:.8rem}
"""

LEGEND = (
    '<div class="legend">'
    '<span class="badge det">🟢 determinística</span> fato reprodutível &nbsp;·&nbsp; '
    '<span class="badge trend">🟡 tendência</span> indicador para comparação relativa, '
    'não valor absoluto</div>'
)


def _badge(cls):
    if cls == "deterministic":
        return '<span class="badge det">🟢</span>'
    if cls == "trend":
        return '<span class="badge trend">🟡</span>'
    return "<span></span>"


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".")
    return str(v)


# formata o VALOR de cada métrica como (número em destaque, explicação curta).
# separar os dois evita que a explicação longa force a largura da coluna e
# esprema a descrição da métrica à esquerda.
def _fmt_metric_parts(key, m):
    v = m.get("value") if isinstance(m, dict) else m
    detail = m.get("detail", {}) if isinstance(m, dict) else {}
    if v is None:
        return "—", ""
    if key == "tool_failure_rate":
        fails, total = detail.get("failCalibrated"), detail.get("totalTools")
        expl = f"{fails} de {total} comandos falharam" if (fails is not None and total) else ""
        return f"{v * 100:.0f}%", expl
    if key == "first_pass_resolution":
        tasks = detail.get("tasks")
        ok = (tasks - detail.get("tasksWithCorrection", 0)) if tasks else None
        expl = f"{ok} de {tasks} tarefas sem correção" if (ok is not None and tasks) else ""
        return f"{v * 100:.0f}%", expl
    if key == "context_usage":
        peak = detail.get("peak")
        expl = f"pico {peak:.0f}%" if isinstance(peak, (int, float)) else ""
        return f"{v:.0f}%", ("em média · " + expl) if expl else "em média"
    if key == "context_discovery_effort":
        disc, impl = detail.get("discovery"), detail.get("implementation")
        expl = f"{disc} explorações para {impl} implementações" if (disc is not None and impl) else "explorações por implementação"
        return _fmt(v), expl
    if key in ("human_correction_rate", "rework_rate"):
        return _fmt(v), "por tarefa"
    if key == "turns_to_resolution":
        return _fmt(v), "turnos em média"
    if key in ("hallucination_intrasession", "hallucination_semantic"):
        events = detail.get("events") if detail.get("events") is not None else detail.get("factCorrections")
        tasks = detail.get("tasks")
        if events is not None and tasks:
            return f"{v * 100:.0f}%", f"{events} caso(s) em {tasks} tarefas"
        return f"{v * 100:.0f}%", "por tarefa"
    if key in ("tool_rejection_rate", "aborted_turn_rate"):
        return f"{v * 100:.0f}%", ""
    if key == "elapsed_seconds":
        return f"{v:.0f}s", "mediana por turno"
    if key == "credits_used":
        sess = detail.get("sessionsWithCredits")
        return f"{v:.1f}", (f"em {sess} sessões" if sess else "créditos")
    if key == "context_truncation":
        tm = detail.get("truncatedMessages")
        ev = detail.get("truncationEvents")
        expl = f"{ev} sumarização(ões), {tm} msgs descartadas" if ev is not None else "por sessão"
        return _fmt(v), expl
    if key == "resolution_efficiency":
        return _fmt(v), "de 1,0 (índice-resumo)"
    return _fmt(v), ""


def _fmt_metric(key, m):
    """Versão em texto simples (usada no modo comparação)."""
    num, expl = _fmt_metric_parts(key, m)
    return f"{num} — {expl}" if expl else num


# unidade da base (campo n) por métrica — o que exatamente foi contado
BASE_UNIT = {
    "first_pass_resolution": "tarefas",
    "human_correction_rate": "tarefas",
    "hallucination_intrasession": "tarefas",
    "hallucination_semantic": "tarefas",
    "rework_rate": "tarefas",
    "turns_to_resolution": "tarefas",
    "resolution_efficiency": "tarefas",
    "tool_failure_rate": "ferramentas/comandos",
    "context_discovery_effort": "ações",
    "context_usage": "amostras",
    "tool_rejection_rate": "aprovações",
    "aborted_turn_rate": "turnos",
    "elapsed_seconds": "turnos medidos",
    "credits_used": "sessões com crédito",
    "context_truncation": "sessões",
}


def _base_label(key, n):
    unit = BASE_UNIT.get(key, "itens")
    if not n:
        return f"sem {unit} no período"
    return f"base: {n} {unit}"


def _metric_row_compare(key, d):
    name = LABELS.get(key, key)
    note = d.get("class") == "trend" and "tendência — comparação relativa" or ""
    delta_pct = d.get("deltaPct")
    direction = d.get("direction", "n/a")
    delta_html = ""
    if delta_pct is not None:
        arrow = "▲" if delta_pct > 0 else ("▼" if delta_pct < 0 else "→")
        cls = "better" if direction == "better" else ("worse" if direction == "worse" else "flat")
        delta_html = f'<span class="delta {cls}">{arrow} {abs(delta_pct):.1f}%</span>'
    n = _base_label(key, d.get("nAfter") or d.get("nBaseline") or 0)
    return (
        f'<div class="metric">{_badge(d.get("class"))}'
        f'<div><span class="mname">{html.escape(name)}</span>'
        f'{f"<span class=mnote>{note}</span>" if note else ""}</div>'
        f'<div class="mval">{_fmt_metric(key, {"value": d.get("baseline")})} → {_fmt_metric(key, {"value": d.get("after")})} '
        f'{delta_html} <span class="n">{n}</span></div></div>'
    )


def _metric_row_single(key, m):
    name = LABELS.get(key, key)
    desc = DESCRIPTIONS.get(key, "")
    value = m.get("value")
    verdict, why = _verdict(key, value)
    verdict_html = (
        f'<span class="verdict {verdict}">{VERDICT_LABEL.get(verdict, "—")}</span>'
        f'<span class="vwhy">{html.escape(why)}</span>'
    )
    example = m.get("example")
    example_html = ""
    if example:
        example_html = (
            f'<div class="example"><span class="lbl">exemplo</span> '
            f'{html.escape(str(example))}</div>'
        )
    num, expl = _fmt_metric_parts(key, m)
    expl_html = f'<div class="mexpl">{html.escape(expl)}</div>' if expl else ""
    return (
        f'<div class="metric-single">{_badge(m.get("class"))}'
        f'<div><span class="mname">{html.escape(name)}</span>'
        f'<span class="mdesc">{html.escape(desc)}</span>'
        f'<div>{verdict_html}</div>'
        f'{example_html}</div>'
        f'<div class="mval"><div class="mnum">{html.escape(num)}</div>'
        f'{expl_html}'
        f'<div class="n">{_base_label(key, m.get("n", 0))}</div></div></div>'
    )


def render_compare(report: dict) -> str:
    diffs = report.get("diffs", {})
    warnings = "".join(f'<div class="warn">⚠ {html.escape(w)}</div>' for w in report.get("warnings", []))
    tc = report.get("taskCount", {})
    overview = (
        '<div class="overview">'
        f'<div class="card"><div class="k">Baseline</div><div class="v">{html.escape(str(report.get("baselineLabel")))}</div><div class="n">{tc.get("baseline")} tarefas</div></div>'
        f'<div class="card"><div class="k">After</div><div class="v">{html.escape(str(report.get("afterLabel")))}</div><div class="n">{tc.get("after")} tarefas</div></div>'
        f'<div class="card"><div class="k">Escopo</div><div class="v" style="font-size:.95rem">{html.escape(str((report.get("scope") or {}).get("workspace","—")))}</div></div>'
        "</div>"
    )
    det_rows = [_metric_row_compare(k, diffs[k]) for k in DETERMINISTIC_ORDER if k in diffs]
    trend_rows = [_metric_row_compare(k, diffs[k]) for k in TREND_ORDER if k in diffs]
    summary_rows = [_metric_row_compare(k, diffs[k]) for k in SUMMARY_ORDER if k in diffs]
    sections = []
    if summary_rows:
        sections.append(
            '<section><h2>⭐ Índice-resumo'
            '<span class="sechint">— leitura geral que combina resultado e esforço</span></h2>'
            f'{"".join(summary_rows)}</section>'
        )
    if det_rows:
        sections.append(
            '<section><h2>🟢 Métricas determinísticas'
            '<span class="sechint">— fatos reprodutíveis do log</span></h2>'
            f'{"".join(det_rows)}</section>'
        )
    if trend_rows:
        sections.append(
            '<section><h2>🟡 Métricas de tendência'
            '<span class="sechint">— indicadores por interpretação; comparação relativa</span></h2>'
            f'{"".join(trend_rows)}</section>'
        )
    return _shell(
        f"{report.get('baselineLabel')} → {report.get('afterLabel')}",
        overview + LEGEND + warnings + "".join(sections),
    )


def render_single(snap: dict) -> str:
    metrics = snap.get("metrics", {})
    period = snap.get("period") or {}
    period_str = f'{period.get("from","?")} → {period.get("to","?")}'
    task_count = snap.get("taskCount") or 0

    warnings = ""
    if task_count < 10:
        warnings = (
            f'<div class="warn">⚠ amostra pequena: {task_count} tarefas '
            f'(&lt; 10) — trate os números como indicativos, não conclusivos</div>'
        )

    # canário de vocabulário: se muitos actionTypes não foram reconhecidos, as métricas
    # de descoberta/implementação podem estar erradas (formato do Kiro mudou).
    unm = snap.get("unmappedActionTypes") or {}
    if unm.get("ratio", 0) >= 0.2:
        top = ", ".join(list(unm.get("byType", {}))[:5]) or "?"
        warnings += (
            f'<div class="warn">⚠ {unm["ratio"]*100:.0f}% dos tool_calls têm '
            f'actionType não reconhecido ({html.escape(top)}). O vocabulário do Kiro '
            f'pode ter mudado — Context Discovery Effort e afins podem estar distorcidos. '
            f'Atualize os aliases em <code>actions.py</code>.</div>'
        )

    kiro_v = snap.get("kiroVersion")
    if kiro_v and kiro_v != "unknown":
        warnings += (
            f'<div class="legend">Kiro {html.escape(str(kiro_v))} · '
            f'skill {html.escape(str(snap.get("skillVersion","?")))}</div>'
        )

    scope = snap.get("scope") or {}
    by_surface = scope.get("bySurface") or {}
    surface_str = " · ".join(f"{k}: {v}" for k, v in by_surface.items()) or "—"
    overview = (
        '<div class="overview">'
        f'<div class="card"><div class="k">Período</div><div class="v" style="font-size:1rem">{html.escape(period_str)}</div></div>'
        f'<div class="card"><div class="k">Tarefas</div><div class="v">{task_count}</div></div>'
        f'<div class="card"><div class="k">Origem (sessões)</div><div class="v" style="font-size:.95rem">{html.escape(surface_str)}</div></div>'
        f'<div class="card"><div class="k">Escopo</div><div class="v" style="font-size:.95rem">{html.escape(str(scope.get("workspace","—")))}</div></div>'
        "</div>"
    )

    det_rows = [_metric_row_single(k, metrics[k]) for k in DETERMINISTIC_ORDER if k in metrics]
    trend_rows = [_metric_row_single(k, metrics[k]) for k in TREND_ORDER if k in metrics]
    summary_rows = [_metric_row_single(k, metrics[k]) for k in SUMMARY_ORDER if k in metrics]
    sections = []
    if summary_rows:
        sections.append(
            '<section><h2>⭐ Índice-resumo'
            '<span class="sechint">— leitura geral que combina resultado e esforço</span></h2>'
            f'{"".join(summary_rows)}</section>'
        )
    if det_rows:
        sections.append(
            '<section><h2>🟢 Métricas determinísticas'
            '<span class="sechint">— fatos reprodutíveis extraídos do log</span></h2>'
            f'{"".join(det_rows)}</section>'
        )
    if trend_rows:
        sections.append(
            '<section><h2>🟡 Métricas de tendência'
            '<span class="sechint">— indicadores por interpretação; use como direção, não valor absoluto</span></h2>'
            f'{"".join(trend_rows)}</section>'
        )

    # Consumo (créditos/tempo) agora sai como métrica 🟢 quando o Kiro registra
    # promptTurnSummaries/elapsedTime. Só mostramos a nota de indisponível se não veio.
    consumption_note = ""
    if "credits_used" not in metrics and "elapsed_seconds" not in metrics:
        consumption_note = (
            '<section><h2>Consumo — Tokens / Credits</h2>'
            '<div class="metric"><span></span><div><span class="mname">Créditos / tempo por sessão</span>'
            '<span class="mnote">não registrados no histórico desta versão do Kiro '
            '(promptTurnSummaries/elapsedTime ausentes)</span></div>'
            '<div class="mval">—</div></div></section>'
        )

    # transparência de metodologia (segmentação)
    seg = snap.get("segmentation") or {}
    method = ""
    if seg:
        method = (
            '<section><h2>Metodologia</h2>'
            f'<div class="metric"><span></span><div><span class="mname">Segmentação de tarefas</span>'
            f'<span class="mnote">estratégia: {html.escape(str(seg.get("strategy","?")))} · '
            f'fronteiras ambíguas: {seg.get("grayBoundaries","?")} · '
            f'tie-breaker: {html.escape(str(seg.get("tieBreaker","none")))}</span></div>'
            f'<div class="mval"></div></div>'
            # explicação didática do score de fronteira
            '<div class="metric"><span></span><div>'
            '<span class="mname">Como decidimos onde uma tarefa começa</span>'
            '<span class="mdesc">Quase todas as métricas são "por tarefa", então o relatório '
            'precisa saber onde cada tarefa começa e termina. O log do Kiro não marca isso, '
            'então inferimos com um <b>score de fronteira</b>: a cada nova mensagem sua, somamos '
            'sinais que indicam se você começou algo novo ou continuou o anterior. Usar só o texto '
            'da mensagem seria frágil (cada um escreve diferente), então o texto pesa pouco — o que '
            'mais conta é o comportamento do próprio Kiro.</span>'
            '<div class="example"><span class="lbl">sinais e pesos</span> '
            'tempo desde a última resposta (35%) · troca dos arquivos mexidos (25%) · '
            'o turno anterior fechou uma entrega (15%) · a próxima ação recomeça explorando o código '
            '(15%) · pistas no texto da mensagem (10%, voto fraco). '
            'Score alto = tarefa nova; baixo = continuação; no meio = "fronteira ambígua" '
            '(que pode ser refinada por LLM, opcional).</div>'
            '</div><div class="mval"></div></div></section>'
        )

    repo_section = _render_repo_section(snap.get("byRepo") or {})
    mode_section = _render_mode_section(snap.get("byMode") or {})

    title = f'{snap.get("label")} · {period_str}'
    return _shell(
        title,
        overview + LEGEND + warnings + "".join(sections) + mode_section + repo_section
        + consumption_note + method,
    )


# métricas-chave mostradas na tabela compacta por repositório
REPO_TABLE_KEYS = [
    ("resolution_efficiency", "Eficiência"),
    ("turns_to_resolution", "Turnos"),
    ("tool_failure_rate", "Falha ferram."),
    ("first_pass_resolution", "1ª tentativa"),
    ("human_correction_rate", "Correções"),
    ("rework_rate", "Retrabalho"),
]


def _render_repo_section(by_repo: dict) -> str:
    """Tabela compacta com as métricas-chave por repositório.

    Só aparece quando há mais de um repositório no período (senão as métricas
    gerais já representam o único repo).
    """
    if not by_repo or len(by_repo) < 2:
        return ""

    # cabeçalho
    head = "".join(f"<th>{html.escape(lbl)}</th>" for _, lbl in REPO_TABLE_KEYS)
    rows = []
    # ordena por nº de tarefas desc
    for ws, data in sorted(by_repo.items(), key=lambda kv: -(kv[1].get("taskCount") or 0)):
        repo_name = os.path.basename(str(ws).rstrip("/")) or str(ws)
        metrics = data.get("metrics", {})
        tc = data.get("taskCount") or 0
        cells = []
        for key, _ in REPO_TABLE_KEYS:
            m = metrics.get(key, {})
            num, _expl = _fmt_metric_parts(key, m)
            verdict, _why = _verdict(key, m.get("value"))
            cells.append(
                f'<td><span class="rv {verdict}">{html.escape(num)}</span></td>'
            )
        rows.append(
            f'<tr><td class="repo">{html.escape(repo_name)}'
            f'<span class="rtc">{tc} tarefas</span></td>{"".join(cells)}</tr>'
        )

    return (
        '<section><h2>Por repositório'
        '<span class="sechint">— mesmas métricas, quebradas por projeto onde o Kiro foi usado</span></h2>'
        '<table class="repotbl"><thead><tr><th>Repositório</th>'
        f'{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></section>'
    )


MODE_LABEL = {"vibe": "Vibe", "spec": "Spec", "cli": "CLI", "?": "(indef.)"}


def _render_mode_section(by_mode: dict) -> str:
    """Tabela por agentMode (vibe/spec/cli). Vibe e spec custam esforço diferente.

    Só aparece quando há mais de um modo no período (review PR #25).
    """
    if not by_mode or len(by_mode) < 2:
        return ""
    head = "".join(f"<th>{html.escape(lbl)}</th>" for _, lbl in REPO_TABLE_KEYS)
    rows = []
    for mode, data in sorted(by_mode.items(), key=lambda kv: -(kv[1].get("taskCount") or 0)):
        metrics = data.get("metrics", {})
        tc = data.get("taskCount") or 0
        cells = []
        for key, _ in REPO_TABLE_KEYS:
            m = metrics.get(key, {})
            num, _expl = _fmt_metric_parts(key, m)
            verdict, _why = _verdict(key, m.get("value"))
            cells.append(f'<td><span class="rv {verdict}">{html.escape(num)}</span></td>')
        rows.append(
            f'<tr><td class="repo">{html.escape(MODE_LABEL.get(mode, str(mode)))}'
            f'<span class="rtc">{tc} tarefas</span></td>{"".join(cells)}</tr>'
        )
    return (
        '<section><h2>Por modo de sessão'
        '<span class="sechint">— Vibe, Spec e CLI custam esforço diferente</span></h2>'
        '<table class="repotbl"><thead><tr><th>Modo</th>'
        f'{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></section>'
    )


def _shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Harness Metrics — {html.escape(title)}</title>
<style>{STYLE}</style></head>
<body>
<header><h1>Harness Metrics</h1>
<div class="sub">{html.escape(title)} · gerado {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div></header>
<main>{body}</main>
<footer>Local-first · métricas 🟢 determinísticas são fato; 🟡 tendências são indicadores relativos.
Créditos/tempo saem quando o Kiro registra promptTurnSummaries/elapsedTime na sessão.</footer>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Renderiza o dashboard HTML")
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.in_path).read_text(encoding="utf-8"))
    t = data.get("_type")
    if t == "harness-metrics-report":
        html_out = render_compare(data)
    elif t == "harness-metrics-snapshot":
        html_out = render_single(data)
    else:
        print(f"[render_html] tipo não reconhecido: {t}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")
    print(f"[render_html] {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
