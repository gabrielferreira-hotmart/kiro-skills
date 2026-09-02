# Privacidade

O histórico do Kiro contém dados sensíveis: prompts, respostas, **conteúdo de arquivos na
íntegra** (via `steering_inclusion` e `tool_result`), paths absolutos e descrições de
tarefa. A skill é **local-first** e trata tudo isso como confidencial por padrão.

## Regras por padrão (sem flags)

1. **Somente leitura** sobre `~/.kiro/`. Nunca escrever, mover ou apagar histórico.
2. **Saída fora de `~/.kiro/`**, em `./.harness-metrics/` (deve estar no `.gitignore`).
3. **O relatório não contém**, por padrão:
   - código-fonte;
   - prompts ou respostas completas;
   - paths absolutos (só nomes de arquivo relativos, quando indispensável);
   - conteúdo de steering/AGENTS.
4. **O relatório contém:** métricas, contagens, scores, IDs anonimizados (hash de
   session-id), timestamps agregados.
5. **Evidência:** os campos `example` de cada métrica **nunca** carregam stdout/stderr cru
   de `tool_result`. Usamos só o que já é do log da IA ou do próprio comando (nome da tool,
   path afirmado, comando de descoberta), e `anonymize.py` ainda trunca `example` a ≤ 200
   chars. Preferir referência por `turno + toolCallId` a texto sempre que possível.

> **`anonymize.py` é passo obrigatório do pipeline**, não opcional. O pipeline canônico é
> collect → segment → metrics → **anonymize** → snapshot → render. Pular a anonimização
> pode publicar path absoluto, nome de repo e trechos sensíveis. O README e o SKILL.md
> mostram o passo explicitamente.

## Anonimização (`anonymize.py`)
- `session-id` → hash curto estável (permite drill-down sem expor o id real).
- Remover/normalizar `workspacePaths`, `rootPaths` e paths absolutos em args/results.
- **Chaves de `byRepo`** (que são paths absolutos) viram basename — não só os valores.
- Redigir tokens/segredos que porventura apareçam (padrões: `AKIA...`, `Bearer ...`,
  `-----BEGIN ... KEY-----`, `ghp_...`) e substituir o home do usuário por `~`.

## LLM externo (judge semântico) — opt-in explícito

O judge semântico (`semantic_eval.py`) está **desligado por padrão**. Ativá-lo requer
`--enable-llm-judge` **e** avisar o usuário de que:

- ativar significa **enviar conversa e/ou trechos de código para um modelo externo** — é
  exfiltração de dados potencialmente proprietários;
- deve-se usar um modelo **diferente** do que gerou as sessões (reduz viés de
  auto-justificação);
- o escopo do envio deve ser o mínimo necessário (o trecho em avaliação, não a sessão
  inteira);
- o resultado é **estimativa** (🟡), não fato.

Sem a flag, todas as métricas 🟡 caem para a variante que **não** usa LLM (heurística
local) ou são omitidas, e o relatório deixa isso explícito.

## Retenção
Snapshots e relatórios ficam no diretório de trabalho do usuário. A skill não envia nada
para lugar nenhum por padrão. Cabe ao usuário versionar ou apagar `.harness-metrics/`.
