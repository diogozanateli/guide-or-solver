# Prompts

Os três prompts do contextualizador são transcrições literais do Apêndice A de:

> Suri et al. (2026). *CodeScout: Contextual Problem Statement Enhancement for
> Software Agents.* Apêndice A.1 (Stage 1), A.2 (Stage 2) e A.3 (Stage 3).

O código do CodeScout não é público; o pipeline em `runner/codescout.py` foi
reimplementado a partir da Seção 4, do Apêndice A e do Algoritmo 1 do artigo.

| Arquivo | Etapa do CodeScout | Placeholders |
|---|---|---|
| `codescout_stage1_scoping.md` | A.1 Exploration Target Identification | `{problem_statement}`, `{file_tree}` |
| `codescout_stage2_analysis.md` | A.2 Content Relevance Analysis | `{problem_statement}`, `{content}`, `{target_type}`, `{target_name}` |
| `codescout_stage3_synthesis.md` | A.3 Problem Statement Synthesis | `{original_ps}`, `{analyses}` |

Adaptações (registradas no `DIARIO_EXPERIMENTO.md`):

- Os placeholders `{target.target_type}` e `{target.target_name}` do artigo foram
  renomeados para `{target_type}` e `{target_name}`.
- No Stage 3, o bloco "For each analyzed target" é montado pelo código em
  `{analyses}`, no formato mostrado no artigo (TARGET, RELEVANCE, ROLE IN ISSUE,
  FIX LOCATION HINTS, EXPLORATION INSIGHTS, ALTERNATIVE HYPOTHESES).

O resolvedor usa o **prompt padrão do mini-swe-agent** (como no artigo, que usou as
configurações padrão do scaffold), recebendo como tarefa a issue original (C1) ou
a especificação aumentada (C2 e C3). A configuração efetiva é gravada em
`results/<modelo>/agent_config.json`.
