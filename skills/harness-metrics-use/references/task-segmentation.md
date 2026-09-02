# Segmentação de tarefas

O log não marca "tarefas" explicitamente. A segmentação as infere. É a base de quase
todas as métricas por-tarefa, então a estratégia usada é registrada no snapshot.

## Por que não regex sozinha

Detectar tarefa nova por frases ("de novo", "não é isso") mede o **vocabulário do dev**,
não o comportamento do Kiro. Cada pessoa fala diferente e em idiomas diferentes — o
resultado ficaria enviesado pelo estilo de quem escreveu, não pela realidade da sessão.

## Modelo: boundary score multi-sinal (v0.3)

Cada prompt de usuário recebe um **score de fronteira** ∈ [0,1]. Score alto ⇒ tarefa
nova; baixo ⇒ continuação. O score combina sinais, a maioria **comportamental e
determinística**:

| Sinal | Peso | O que mede | Determinístico? |
|---|---|---|---|
| `gap` | 0.35 | tempo entre a resposta anterior e o prompt (interpola 20 min → 1 h) | ✅ |
| `files` | 0.25 | troca dos arquivos tocados (1 − Jaccard entre blocos) | ✅ |
| `stopReason` | 0.15 | turno anterior fechou em `end_turn` (entrega concluída) | ✅ |
| `discovery` | 0.15 | próximo bloco recomeça com leitura/busca (readFiles/search/mcp) | ✅ |
| `text` | 0.10 | regex de correção/follow-up — **voto fraco** | parcial |

A regex continua existindo, mas com peso 0.10 — vira **um voto entre cinco**, então o
estilo do dev deixa de dominar.

### Limiares
- `score ≥ 0.60` → tarefa nova, `confidence: high`
- `score ≤ 0.35` → continuação, `confidence: high`
- entre os dois → **zona cinza**, `confidence: low` (default conservador = continuação)

Regra dura: prompt logo após `pending_interaction` nunca abre tarefa (é resposta a uma
pergunta do agente).

## Tie-breaker por LLM (opcional, opt-in)

`segment_llm.py` refina **apenas** as fronteiras `confidence: low`. Para cada uma, envia
só o par de prompts (anterior + atual), truncado, e pergunta "tarefa nova ou
continuação?". Mantém 80–90% da segmentação determinística e usa o LLM cirurgicamente.

- OFF por padrão; exige `--enable-llm-judge`.
- Envia o mínimo (par de mensagens), nunca a sessão inteira. Ver `privacy.md`.
- `classify_boundary(prev, next)` é ponto de extensão — acoplar um provedor de LLM
  (idealmente diferente do que gerou as sessões, para reduzir viés).
- O snapshot registra `tieBreaker` e `llmRefined` para dar transparência de quanto do
  resultado dependeu de interpretação.

## Transparência
O snapshot e o relatório expõem: estratégia, nº de fronteiras cinzas e se houve
tie-breaker. Nunca esconder a metodologia — o leitor precisa saber quanto é fato e quanto
é inferência.

## Riscos residuais
- **Sinais fracos em sessões curtas:** poucos arquivos/turnos reduzem o poder de `files`
  e `discovery`; o score recai mais sobre `gap`.
- **Gaps enganosos:** pausa longa no meio de uma tarefa (almoço) pode inflar `gap`. Por
  isso `gap` tem peso alto mas não decide sozinho.
- **Zona cinza sem LLM:** default conservador (continuação) pode subcontar tarefas; o
  tie-breaker opcional existe justamente para esses casos.
