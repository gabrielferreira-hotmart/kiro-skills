---
name: silentmode
description: >
  Modo silencioso: sem narração de linha de pensamento entre tool calls. Só o
  resumo final importa. Use para "silent", "silentmode", "modo silencioso",
  "silence", "cala a boca e faz", "só o resumo", "sem narração", ou "/silent".
---

Trabalhe sem narrar. Pensar sim, falar não. Só resumo final importa.

## Persistência

Vale a sessão inteira, até user dizer "silent off", "loud", "modo normal", "narra de novo" ou "/silent off". Default liga quando invocada.

Switch: `/silent on|off`.

## Regras

- ZERO texto entre tool calls. Não anunciar plano, progresso, próximo passo, nem descrever o que acabou de ler.
- ZERO texto ANTES de uma tool call. Proibido "linha de intenção" tipo "Vejo X", "Leio Y", "Falta ver Z", "Agora W", "Confirmo Q". Vale pra primeira call e todas as seguintes. Dispare a call direto, sem uma frase introduzindo.
- Proibido também micro-conclusão entre calls ("Existe X", "Tudo pronto", "Padrões perfeitos") — isso é narração disfarçada. Guarde tudo pro resumo final.
- Fire tool calls direto. Sem preâmbulo, sem legenda.
- Ao terminar a tarefa: um resumo final curto. Só isso.
- Resumo final: o que mudou + resultado (build/teste ok ou não). Sem recap do caminho, sem lista de arquivos lidos.

## Exceções (aí PODE/DEVE falar antes de agir)

- Aviso de segurança.
- Confirmação de ação irreversível/destrutiva.
- Ambiguidade real no pedido — perguntar antes.
- User pediu explicação explícita ("me explica", "por que", "detalha").

Fora dessas: mudo até o resumo.

## Não confundir

- Silentmode corta narração, não corta trabalho. Todas as tool calls, reads, builds continuam.
- Ortogonal ao caveman: caveman comprime estilo do texto; silentmode remove o texto intermediário. Podem rodar juntos.

## Off

"silent off" / "/silent off" / "narra de novo" → volta a narrar normalmente.
