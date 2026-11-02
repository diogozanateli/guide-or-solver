# Diário do Experimento — Guide or Solver?

Registro cronológico de decisões, configurações, resultados e incidentes, para
apoiar a escrita das seções de Metodologia, Resultados, Ameaças à Validade e
Disponibilidade de Artefatos. Atualizar a cada etapa; não apagar entradas antigas
(se algo mudar, registrar a mudança com data e motivo).

Legenda: `[PREENCHER]` = pendente · **Artigo:** = onde a informação entra no texto.

Os blocos entre `<!-- AUTO:... -->` e `<!-- /AUTO:... -->` são reescritos por
`scripts/update_diary.py` (o notebook o chama ao fim de cada etapa). **Não edite dentro
deles**; escreva observações fora dos marcadores.

---

## 1. Visão geral do desenho

- **Objetivo:** verificar se um agente de LLM é mais eficaz como resolvedor
  autônomo de issues ou como contextualizador que orienta a resolução.
- **Condições** (mesmo agente resolvedor, mesma configuração, mesmos limites):
  - **C1 — Autônomo:** recebe apenas o texto original da issue.
  - **C2 — Orientação descritiva:** recebe a especificação aumentada pelo CodeScout
    **sem** a subseção "Implementation Suggestions".
  - **C3 — Orientação com implementação:** recebe a especificação aumentada completa
    (replicação do CodeScout).
- **RQ1:** efeito das orientações na resolução (taxa de resolução, ações, tokens).
- **RQ2:** precisão da localização indicada pela orientação (arquivo e função).
- **RQ3:** relação das soluções com a correção humana (CodeBLEU, volatilidade).
- **Sem participantes humanos:** o resolvedor em C2/C3 atua como substituto de um
  desenvolvedor que recebe a orientação. **Artigo:** Introdução e Ameaças.

---

## 2. Infraestrutura e ambiente

**Artigo:** Seção 3.1 (Materiais e Ferramentas) e Disponibilidade de Artefatos.

| Item | Valor | Fonte |
|---|---|---|
| Plataforma de execução | Kaggle Notebooks (gratuito), GPU habilitada, Internet ativada | — |
| GPU | 2× NVIDIA Tesla T4, 15360 MiB cada, driver 580.178.04 | `results/environment.txt` |
| CPU | Intel Xeon @ 2.00 GHz, 4 vCPU | `results/environment.txt` |
| RAM | 31 GiB | `results/environment.txt` |
| Sistema operacional | Ubuntu 24.04.4 LTS | `results/environment.txt` |
| Python | 3.13.16 | `results/environment.txt` |
| Isolamento | Um ambiente virtual `uv venv` por instância (Kaggle não oferece Docker) | decisão |
| Repositório do código | `https://github.com/diogozanateli/guide-or-solver` | — |

**Custo:** sem APIs pagas, licenças ou infraestrutura contratada. Limites gratuitos
do Kaggle: cerca de 30 h de GPU por semana e sessões de até 12 h. Não significa
custo computacional zero (ver Seção 3.1 do artigo).

---

## 3. Modelo e runtime

**Artigo:** Seção 3.1; diretriz *Report Model Version, Configuration*.

**Decisão (2026-11-02):** dois modelos de pesos abertos, de famílias diferentes,
executados sobre o mesmo corpus e as mesmas três condições. Gemini foi
considerado e descartado: é proprietário (contradiz execução local e sem API paga
da Seção 3.1), o plano gratuito tem limites de requisição incompatíveis com
agentes e a data de corte mais recente reduziria o período de mineração. Variantes
`deepseek-r1` foram descartadas por serem destilações sobre Qwen/Llama.
Resultados separados em `results/<modelo>/`.

Runtime: Ollama 0.40.13 · `OLLAMA_KEEP_ALIVE=-1` (mantém os modelos carregados).

| Item | Qwen2.5-Coder 7B | DeepSeek-Coder-V2 16B (Lite) |
|---|---|---|
| Tag Ollama | `qwen2.5-coder:7b` | `deepseek-coder-v2:16b` |
| Licença | Apache 2.0 | DeepSeek License `[PREENCHER — confirmar]` |
| Digest (ID Ollama) | `dae161e27b0e` | `63fb193b3a9b` |
| Arquitetura / parâmetros | qwen2 / 7.6B (denso) | `[PREENCHER]` / 16B MoE, ~2.4B ativos `[confirmar]` |
| Quantização | Q4_K_M (4.7 GB em disco; 6.6 GB na GPU) | `[PREENCHER]` (8.9 GB em disco) |
| Contexto máximo do modelo | 32768 | `[PREENCHER]` |
| Execução | 100% GPU | `[PREENCHER]` |
| Velocidade medida | ~32 tokens/s | `[PREENCHER]` |
| Carga inicial | ~94 s | `[PREENCHER]` |
| Data de corte de treinamento | `[PREENCHER — model card]` | `[PREENCHER — model card]` |

<!-- AUTO:modelos -->
_Ainda não executado._
<!-- /AUTO:modelos -->

**Parâmetros de geração** (`config/experiment.yaml`):

| Parâmetro | Valor |
|---|---|
| temperature | 0.0 |
| seed | 42 |
| num_ctx | 32768 (definido explicitamente; o padrão do Ollama trunca o contexto) |
| Execuções por condição (k) | 1 `[PREENCHER se mudar]` |

**Bibliotecas** (versões instaladas no Kaggle):

| Pacote | Versão |
|---|---|
| mini-swe-agent | 2.4.6 |
| litellm | 1.93.2 |
| codebleu | 0.7.0 |
| demais | ver `pip freeze` em `results/environment.txt` `[PREENCHER]` |

O período de mineração começa em 2025-01-01, depois da data de corte de ambos os
modelos (lançados em 2024), para mitigar contaminação. Confirmar as datas nas
model cards antes de citar.

---

## 4. Contextualizador (CodeScout) e resolvedor

**Artigo:** Seção 3.2; diretriz *Report System and Prompt Design*.

**Decisão:** o contextualizador é uma **reimplementação do CodeScout** (Suri et al.,
2026), feita a partir da Seção 4, do Apêndice A (prompts, transcritos literalmente
em `prompts/`) e do Algoritmo 1. O código original não é público.

| Etapa | Implementação (`runner/codescout.py`) |
|---|---|
| Estrutura do repositório | Árvore de arquivos (`git ls-files`) + índice AST de classes e funções para recuperar o código dos alvos |
| Stage 1 — Exploration Target Identification | Prompt A.1 com a issue e a árvore; 5–10 alvos `target_type`/`target_name`/`reasoning` |
| Stage 2 — Content Relevance Analysis | Prompt A.2, uma chamada por alvo recuperado; `RELEVANCE X/10` + 4 seções |
| Filtro | Mantém análises com relevância ≥ **τ = 5** |
| Stage 3 — Problem Statement Synthesis | Prompt A.3; seções Issue Description, Reproduction Steps, Expected Behavior, Exploration Hints, Fix Hints |
| Chamadas ao LLM | 2 + nº de alvos recuperados (o artigo relata ≈ 9) |

**Condições:**

| Condição | Tarefa entregue ao resolvedor |
|---|---|
| C1 | Issue original (título + corpo) — equivale ao *Default* do CodeScout |
| C2 | Especificação aumentada **sem** a subseção "Implementation Suggestions" de Fix Hints |
| C3 | Especificação aumentada completa (replicação do CodeScout) |

**Decisão (opção a):** C2 e C3 vêm da **mesma** execução do CodeScout; C2 é obtida
removendo a subseção "Implementation Suggestions" (item, sub-itens e blocos de
código) após a síntese. Assim a única diferença entre C2 e C3 é a sugestão de
implementação. Verificação adicional: blocos de código fora de "Reproduction Steps"
que não vêm da issue original são sinalizados (`c2_contains_code`).

**Resolvedor:** mini-swe-agent com a **configuração padrão** do pacote (como no
artigo), recebendo a issue (C1) ou a especificação aumentada (C2/C3) como tarefa,
em substituição à issue. Configuração efetiva em `results/<modelo>/agent_config.json`.

| Item | Valor |
|---|---|
| Framework | mini-swe-agent 2.4.6 (apenas bash), configuração padrão |
| Limite de ações — resolvedor | 50 (o artigo usou o padrão do Mini-SWE-Agent; limite definido por custo computacional) |
| Timeout por comando | 120 s |
| Prevenção de vazamento | clone apenas da revisão base (`--depth 1`), sem histórico futuro; o patch humano e os testes FAIL_TO_PASS não são fornecidos |
| Localização para a RQ2 | arquivos e funções citados em Exploration Hints e Fix Hints → High Confidence Locations |

**Lacunas do artigo e escolhas feitas (declarar no artigo):**

- **τ não é informado** no CodeScout; adotado τ = 5 (escala 0–10).
- O prompt A.1 pede "exactly 5–10 targets", mas o texto (Seção 4.2) cita |T| ≤ 15;
  seguido o prompt (máximo 10).
- O grafo de conhecimento é descrito na Seção 4.1, mas o prompt A.1 recebe apenas a
  árvore de arquivos (`{file_tree}`); o grafo foi usado apenas para recuperar o
  código dos alvos.
- Limites de tamanho para caber no contexto de 32k tokens: árvore ≤ 60.000
  caracteres (removendo primeiro arquivos não-.py, depois testes/docs) e código de
  cada alvo ≤ 12.000 caracteres. Truncamentos ficam registrados.
- Se nenhuma análise atinge τ, a síntese recebe a indicação "(no code analysis passed
  the relevance threshold)"; o artigo não descreve esse caso.
- O artigo usou modelos maiores (GPT-5-mini, DeepSeek R1, Qwen3 Coder 480B); aqui
  são modelos abertos de 7B e 16B, quantizados.

Alterações nos prompts após o piloto: `[PREENCHER — data, mudança, motivo]`

---

## 5. Seleção de repositórios

**Artigo:** Seção 3.1 (parágrafo de critérios) e Ameaças (validade externa).

Script: `mining/00_select_repos.py` → `data/repos.csv`.

| Critério | Regra |
|---|---|
| C10 | Não consta em `config/excluded_repos.csv` (exclusão manual com justificativa) |
| C1 | Linguagem principal Python, ≥ 1.000 estrelas, não fork, não arquivado, atividade desde 2025-01-01 (busca do GitHub ordenada por estrelas; máx. 1.000 resultados) |
| C7 | Criado antes de 2023-01-01 |
| C2 | Tamanho ≤ 200 MB |
| C3 | `pyproject.toml`, `setup.py` ou `setup.cfg` na raiz |
| C8 | ≥ 20 arquivos de teste (`test_*.py` ou `*_test.py`) |
| C4 | Usa pytest (configuração, `conftest.py` ou dependência declarada) |
| C5 | Sem extensões compiladas (.c, .cpp, .pyx, .rs, Cargo.toml, ext_modules) |
| C9 | Sem dependências pesadas de ML/GPU (torch, tensorflow, jax, transformers, onnxruntime, etc.) |
| C6 | ≥ 10 PRs mesclados vinculados a issues entre 2025-01-01 e 2026-10-31 |
| Corte | Primeiros **20** aprovados por número de estrelas |

Resultados:

<!-- AUTO:selecao -->
_Ainda não executado._
<!-- /AUTO:selecao -->

**Histórico:**
1. Uma primeira mineração usou uma lista de 24 repositórios escolhida por
   conveniência (26 candidatos). **Descartada** em favor de critérios reprodutíveis.
2. A primeira versão dos critérios (C1–C6, 40 repositórios) aprovou coleções
   educacionais (TheAlgorithms/Python), repositórios de *skills*/prompts para agentes
   (spec-kit, BMAD-METHOD, academic-research-skills, Agent-Reach etc.), projetos
   criados em 2025–2026 e projetos com dependências pesadas de ML (ComfyUI,
   LlamaFactory, keras, ultralytics, gradio). A mineração foi interrompida e os
   candidatos descartados. Foram adicionados C7–C10 e reduzido o corte para 20
   repositórios.

**Justificativa de C7 (para o artigo):** repositórios criados antes de 2023 têm
histórico de manutenção anterior à popularização de assistentes de código, o que
favorece projetos estabelecidos e reduz a proporção de projetos cujo
desenvolvimento é majoritariamente feito por agentes.

---

## 6. Mineração de issues

**Artigo:** Seção 3.2 (Procedimentos).

Script: `mining/01_mine.py` → `data/candidates.jsonl`.

- Período: 2025-01-01 a 2026-10-31 (PRs mesclados).
- Vínculo PR → issue: texto do PR com "fixes/closes/resolves #N".
- Filtros: issue com texto; PR altera código e testes; até 3 arquivos de código
  (`max_code_files`); até **10** candidatos por repositório (`max_candidates_per_repo`).
- **P1:** autor do PR (ou de algum commit) não é bot nem agente de IA conhecido
  (`[bot]`, Copilot, copilot-swe-agent, devin-ai-integration, google-labs-jules,
  openhands-agent, etc.).
- **P2:** título, descrição e mensagens de commit sem marcas de geração por IA
  ("Generated with Claude Code", `Co-authored-by: Claude/Copilot/Cursor/...`,
  "Copilot agent", "OpenHands", etc.).
- Todo PR avaliado e o motivo do descarte ficam em `data/mining_log.csv`.
- Revisão base: primeiro pai do merge commit.

<!-- AUTO:mineracao -->
_Ainda não executado._
<!-- /AUTO:mineracao -->

---

## 7. Validação das instâncias

**Artigo:** Seção 3.2 e tabela de caracterização do corpus.

Script: `mining/02_validate.py` → `data/instances.jsonl`, `data/exclusions.csv`.

- FAIL_TO_PASS: falham na revisão base com os testes do PR e passam com a correção.
- PASS_TO_PASS: passam nas duas versões.
- 3 execuções por versão; resultados diferentes entre execuções → `testes_instaveis`.

<!-- AUTO:validacao -->
_Ainda não executado._
<!-- /AUTO:validacao -->

---

## 8. Piloto

**Artigo:** normalmente não entra como resultado; justifica os parâmetros finais.

| Item | Valor |
|---|---|
| Data | `[PREENCHER]` |
| Instâncias | `[PREENCHER]` |
| Tempo médio por instância (C1+C2+C3+contextualizadores) | `[PREENCHER]` |
| Problemas encontrados | `[PREENCHER]` |
| Ajustes feitos | `[PREENCHER]` |
| Data do congelamento do `experiment.yaml` (commit) | `[PREENCHER]` |

---

## 9. Execução completa

| Bloco | Data | Instâncias | Sessão Kaggle (h) | Observações |
|---|---|---|---|---|
| `[PREENCHER]` | | | | |

Falhas, status de encerramento e violações da regra "sem código" em C2:

<!-- AUTO:execucao -->
_Ainda não executado._
<!-- /AUTO:execucao -->

Tratamento das falhas e violações: `[PREENCHER]`

---

## 10. Resultados

Arquivos: `results/<modelo>/rq1_summary.csv`, `rq2_summary.csv`, `rq3_summary.csv`, `stats.csv`.

<!-- AUTO:resultados -->
_Ainda não executado._
<!-- /AUTO:resultados -->

Observações qualitativas (exemplos interessantes de orientações e patches):
`[PREENCHER — instance_id e o que chamou atenção]`

---

## 11. Ameaças à validade (registrar conforme surgirem)

**Artigo:** seção de Ameaças; diretriz *Report Limitations and Mitigations*.

- **Não determinismo:** temperature 0 e seed fixa; k = 1 execução por condição.
- **Contaminação:** issues a partir de 2025; não é possível garantir que os
  repositórios não estejam no treinamento do modelo.
- **Resolvedor como substituto humano:** os ganhos de C2/C3 indicam utilidade da
  orientação para um agente, não necessariamente para desenvolvedores.
- **Modelos:** dois modelos abertos, pequenos (7B denso e 16B MoE) e quantizados;
  resultados podem não valer para modelos maiores ou proprietários.
- **Seleção de repositórios:** favorece projetos Python populares, maduros e sem
  código nativo.
- **Testes como oráculo:** patches podem passar nos testes sem estarem corretos
  (validação humana `[PREENCHER — se for feita]`).
- **Autoria humana da correção de referência:** P1/P2 removem PRs de bots e com
  marcas explícitas de IA, mas não detectam uso não declarado de assistentes; a
  "correção humana" pode ter sido produzida com apoio de LLMs.
- **CodeBLEU:** similaridade com a referência não implica equivalência funcional.
- **Nota de relevância do CodeScout:** é autoavaliada pelo próprio modelo no Stage 2,
  sem rubrica (como no artigo original), e τ = 5 não vem do artigo. A distribuição
  das notas depende do modelo (o próprio CodeScout relata isso), então o mesmo τ
  filtra quantidades diferentes de contexto para Qwen e DeepSeek. Respostas sem nota
  no formato esperado são descartadas. Distribuição por modelo: seção 9 (automática).
- **Isolamento por `venv` e não por contêiner:** dependências do sistema
  compartilhadas entre instâncias.
- `[PREENCHER — novas ameaças observadas]`

---

## 12. Incidentes técnicos e correções

| Data | Etapa | Problema | Solução |
|---|---|---|---|
| 2026-11-02 | Setup | `codebleu 0.7.0` incompatível com `tree-sitter>=0.23` fixado no `requirements.txt` | Removido o pin de `tree-sitter`; o código usa `ast` para extrair funções |
| 2026-11-02 | Setup | Primeira chamada ao modelo demorou ~94 s | Carregamento do modelo; `OLLAMA_KEEP_ALIVE=-1` para mantê-lo na GPU |
| 2026-11-02 | Setup | Servidor Ollama iniciado em segundo plano pelo script não respondia | Reiniciado com `subprocess.Popen(..., start_new_session=True)` |
| 2026-11-02 | Git | Push do Kaggle negado (403) | Token fine-grained sem permissão *Contents: Read and write*; corrigido |
| 2026-11-02 | Mineração | Lista inicial de repositórios sem critério reprodutível | Criado `00_select_repos.py` (critérios C1–C6) |
| `[PREENCHER]` | Mineração | Primeira versão dos critérios aprovou coleções, repositórios de *skills* para agentes e projetos com dependências de ML | Adicionados C7–C10 (criação < 2023, ≥ 20 arquivos de teste, sem dependências pesadas, exclusão manual) e P1–P2 (PRs de bots/IA); corte reduzido para 20 repositórios e 10 PRs por repositório |
| `[PREENCHER]` | Desenho | Contextualizador e prompts próprios não seguiam o CodeScout, que é a base de replicação | Reimplementado o CodeScout (prompts do Apêndice A, Algoritmo 1, τ = 5); C2 = saída sem "Implementation Suggestions"; resolvedor com configuração padrão do mini-swe-agent |
| `[PREENCHER]` | Mineração | Queda de conexão com a API do GitHub (`RemoteDisconnected`) interrompeu `01_mine.py` durante o `scrapy/scrapy` | `common/github.py` passou a repetir requisições após falhas de conexão/timeout (até 8 tentativas, espera crescente até 300 s); o download de diffs passou a usar a mesma função. A mineração foi retomada do ponto de parada |
| `[PREENCHER]` | Kaggle | Notebook executado com *Save & Run All* reaproveitou o `data/repos.csv` antigo (C1–C6) e falhou por falta da coluna `created_at` | `00_select_repos.py` grava `data/repos_criteria.json`; o notebook refaz a seleção (e apaga candidatos/instâncias dependentes) quando os critérios mudam |
| `[PREENCHER]` | | | |

---

## 13. Artefatos a publicar

**Artigo:** seção *Disponibilidade de Artefatos*.

- [ ] `data/repos.csv`, `candidates.jsonl`, `instances.jsonl`, `exclusions.csv`
- [ ] `config/experiment.yaml` congelado (hash do commit: `[PREENCHER]`)
- [ ] Prompts completos (`prompts/`)
- [ ] Trajetórias completas, orientações e patches (`results/<instancia>/`)
- [ ] Métricas por instância e resumos (`results/*.csv`)
- [ ] `results/environment.txt`
- [ ] DOI no Zenodo: `[PREENCHER]` · Licença: `[PREENCHER — ex.: MIT para código, CC-BY 4.0 para dados]`
