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
| Execução | 100% GPU | 5%/95% CPU/GPU; 23 GB carregado com `num_ctx` 32768 (`ollama ps`, 2026-11-04) |
| Capacidades (`/api/show`, 2026-11-03) | completion, **tools**, insert (template contém `.Tools`) | completion, insert — **sem tools** (template sem `.Tools`) |
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

Alterações nos prompts após o piloto: no segundo piloto (DeepSeek) foram acrescentadas regras ao final do
`system_template` ("Additional Execution Rules") e do `instance_template` ("Additional Progress Rules"),
para reduzir repetição de comandos; a mudança não resolveu o problema (ver 14.8) e foi **removida** na
reorganização posterior. A configuração vigente é a padrão do pacote, `mini_textbased.yaml`, sem texto
adicional. Data da alteração e da remoção: `[PREENCHER]`. Qualquer regra anti-repetição futura deve ser
tratada como variante declarada, idêntica nas três condições (ver 14.13).

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
| Data | 2026-11-03 a 2026-11-04 (diagnósticos e execuções, datas inferidas dos arquivos); datas dos pilotos 1 e 2: `[PREENCHER]` |
| Instâncias | 1 (`yt-dlp__yt-dlp-16919`) × 2 modelos; ainda não é um piloto de várias instâncias |
| Tempo médio por instância (C1+C2+C3+contextualizadores) | Qwen, pipeline corrigido: 904,9 s (C1 172,7 + C2 278,0 + C3 244,0 + CodeScout 210,2), **sem** o tempo de `setup_venv` (por execução, não incluído em `duration_s`). Valor não representativo: as três condições terminaram no limite de 50 ações |
| Problemas encontrados | Resumo na Seção 12; detalhes e evidências em 14.7–14.12 |
| Ajustes feitos | Modo textual com `ollama_chat/` para os dois modelos; leitura do `exit_status` do dict; contagem de chamadas/tokens por interceptação; auditoria de vazamento; `WORK` fora do repositório (14.10) |
| Data do congelamento do `experiment.yaml` (commit) | `[PREENCHER]` — **não congelar** antes de concluir as verificações de 14.13 |

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
- **Gabarito acessível ao agente (observado em 2026-11-04):** `data/instances*.jsonl` contém
  `code_patch`, `test_patch`, `merge_commit`, `FAIL_TO_PASS` e `PASS_TO_PASS`. O agente executa comandos
  sem sandbox (`LocalEnvironment`) e, nos pilotos, o checkout ficava em `work/` **dentro** do repositório
  do projeto. Mitigação: `WORK` passou a `/tmp/gos_work` e cada execução registra `leak_audit` (busca por
  `/kaggle`, `gos/data`, `instances*.jsonl` e nomes dos campos do gabarito nos comandos do agente);
  execuções com `leak_audit` não vazio devem ser invalidadas. Limitação residual: o processo ainda enxerga o
  sistema de arquivos do notebook. Nas execuções observadas depois da correção, `leak_audit = []`.
- **Agente sem isolamento:** no piloto o agente executou `sudo apt-get install` no ambiente do notebook.
  Foi inofensivo, mas mostra que comandos arbitrários rodam sem contenção (Kaggle não oferece Docker).
- **Degeneração por repetição:** com modelos pequenos e `temperature = 0`, as execuções observadas
  terminaram em `LimitsExceeded` com poucos comandos distintos (14.3). Se isso se repetir no corpus, a taxa de
  resolução pode ficar próxima de zero nas três condições e perder poder discriminativo; definir as métricas
  primárias (localização, degeneração) **antes** de rodar o corpus completo.
- **Modo textual por restrição do modelo:** o DeepSeek-Coder-V2 não declara suporte a tools no Ollama,
  então o resolvedor usa o modo textual (`ollama_chat/` + bloco de código) nos dois modelos. Os resultados não
  se estendem a modelos usados com tool calling nativo.
- **Métricas de uso:** nos pilotos 1 e 2, `llm_calls` e tokens subestimavam chamadas com erro de formato
  (14.8). A contagem atual intercepta `litellm.completion`; validar com uma execução que tenha erros de formato.
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
| `[PREENCHER]` | Resolvedor (pilotos 1 e 2) | O campo `status` ficou `'exit_status'` em todas as execuções | `agent.run()` (mini-swe-agent v2) retorna um dict `{exit_status, submission}`; `status, output = agent.run(...)` desempacotava as **chaves**. O status real foi recuperado da última mensagem `exit` da trajetória (14.8); o código passou a ler `result["exit_status"]` |
| `[PREENCHER]` | Resolvedor | Classe de modelo de tool calling (`LitellmModel`) com o template **textual** (`default.yaml`, bloco `mswea_bash_command`) | Incompatibilidade de configuração confirmada; efeito causal sobre a falha não demonstrado (14.9, teste 8). Pipeline migrado para `LitellmTextbasedModel` + `mini_textbased.yaml` |
| 2026-11-03 | Resolvedor (DeepSeek) | `RepeatedFormatError` após 1 ação: o modelo não produz `tool_calls` (sem suporte a tools no Ollama) | Modo textual com `ollama_chat/` para os dois modelos |
| `[PREENCHER]` | Métricas | `llm_calls` = 1 no DeepSeek, mas a trajetória mostra ≥ 4 consultas (respostas rejeitadas pelo parser não viram mensagens do assistente) | Contagem por interceptação de `litellm.completion`; resultado grava `usage_source` |
| `[PREENCHER]` | Métricas | Duração agregada de C2/C3 (552,7 s e 546,4 s) divergia das individuais (12,9 s e 6,6 s) | A diferença é idêntica (539,8 s) nas duas: tempo do CodeScout somado a ambas. Não somar C2 + C3 ao agregar custo |
| 2026-11-03 | Diagnóstico | `Cost must be > 0.0` abortava a primeira chamada nos testes isolados de agente | `cost_tracking="ignore_errors"` (e `MSWEA_COST_TRACKING`); testes anteriores a isso são inválidos |
| 2026-11-04 | Segurança experimental | Gabarito em `data/` e checkout dentro do repositório (ver Seção 11) | `WORK` em `/tmp/gos_work`; auditoria `leak_audit` por execução |
| 2026-11-04 | Pipeline | Checkpoint por arquivo pularia os `C*_run0.json` dos pilotos antigos; `agent_config.json` apontava para `default.yaml` | Pilotos movidos para `results_pilotos_descartados/`; `agent_config.json` regravado a cada execução, com hash da configuração |
| 2026-11-04 | Git | `git pull --rebase` falhava com arquivos modificados | `git pull --rebase --autostash` |
| 2026-11-04 | Kaggle | `ModuleNotFoundError: minisweagent` após reinício da sessão; `litellm.__version__` inexistente | Reinstalar com versões fixas (`mini-swe-agent==2.4.6`, `litellm==1.93.2`); ler versões com `importlib.metadata` |
| 2026-11-04 | Kaggle | Célula longa sem saída parecia travada (`sh()` só imprime ao final) | Execução em segundo plano com log (`nohup`) e, no `run_condition.py`, linha por passo e `logs/*.steps.jsonl` |
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


---

## 14. Atualizações do acompanhamento — 2026-11-04 a 2026-11-06

> Esta seção complementa o registro anterior sem apagar as decisões e os resultados
> já documentados. Os resultados descritos abaixo são **pilotos/diagnósticos**, não
> resultados finais do experimento. Execuções com falhas de configuração ou
> comportamento anômalo devem permanecer identificadas como descartadas ou
> exploratórias.

### 14.1. Origem e seleção do corpus — esclarecimento (2026-11-04)

A seleção de repositórios implementada em `mining/00_select_repos.py` **não utiliza
o SWE-bench Verified como fonte**. A função `search_repos()` consulta diretamente a
API de busca de repositórios do GitHub (`/search/repositories`), com filtros de
linguagem Python, estrelas, fork, arquivamento e data de atividade. Os repositórios
encontrados são então avaliados sequencialmente pelos critérios C10, C1, C7, C2,
C3, C8, C4, C5, C9 e C6.

A etapa posterior de mineração de issues/PRs é implementada em
`mining/01_mine.py`. Portanto, o corpus é construído pelo próprio pipeline de
mineração e validação; não é uma seleção de instâncias do SWE-bench Verified.
**Artigo:** descrever a fonte como API do GitHub e explicitar os critérios próprios
de seleção. Não atribuir ao corpus a curadoria ou as propriedades de validação do
SWE-bench.

### 14.2. Visualização e comparação das saídas do CodeScout (2026-11-04)

Foi inspecionado o conteúdo de `codescout.json` para a instância
`yt-dlp__yt-dlp-16919`.

Na saída observada:
- C2 e C3 apresentam o mesmo conteúdo em `Issue Description`,
  `Reproduction Steps`, `Expected Behavior`, `Exploration Hints`, `Fix Hints` e
  `Alternative Hypotheses`.
- C3 contém adicionalmente a subseção `Implementation Suggestions`; C2 não a
  contém.
- As sugestões de C3 indicam alterações concretas relacionadas ao argumento
  `_allowed_exts`, incluindo a função lambda em `validate_options` e o tratamento
  em `replace_extension`.

A inspeção é compatível com a implementação planejada: C2 e C3 derivam da mesma
execução do CodeScout e a diferença pretendida é a presença/ausência de
`Implementation Suggestions`. **Verificação pendente:** executar uma comparação
automatizada dos textos para confirmar que, após remover integralmente essa
subseção de C3, o restante é idêntico. Também permanece útil conferir se os sete
alvos mantidos aparecem adequadamente na especificação final.

### 14.3. Diagnóstico do resolvedor em modo texto (2026-11-04)

Após problemas observados na integração anterior em modo nativo — incluindo
respostas em que texto de raciocínio era interpretado como comando de shell —,
o resolvedor foi migrado para a integração textual do mini-swe-agent:
`LitellmTextbasedModel`, configuração `mini_textbased.yaml` e prefixo de modelo
`ollama_chat/`.

Um teste isolado (`DefaultAgent` com `LitellmTextbasedModel`) demonstrou que o
agente consegue executar comandos e receber observações do ambiente. Entretanto,
também repetiu comandos de inspeção (`ls`) mesmo após receber a saída, indicando
que a repetição de ações não estava restrita à integração nativa.

Em uma execução diagnóstica posterior, as três condições atingiram o limite de
50 ações/chamadas, sem erros registrados do LiteLLM e sem gerar patch:

| Condição | Status | Ações / chamadas | Tokens de entrada | Tokens de saída | Duração | Patch |
|---|---:|---:|---:|---:|---:|---|
| C1 | `LimitsExceeded` | 50 / 50 | 426.433 | 3.417 | 172,7 s | Vazio |
| C2 | `LimitsExceeded` | 50 / 50 | 650.666 | 4.159 | 278,0 s | Vazio |
| C3 | `LimitsExceeded` | 50 / 50 | 410.473 | 4.082 | 244,0 s | Vazio |

Outros indicadores registrados:
- `llm_errors = 0` nas três condições;
- `venv_ok = True`;
- `leak_audit = []`;
- C1 repetiu principalmente `man yt-dlp` e `sudo apt-get install man-db`;
- C2 repetiu buscas `grep` por `allow-unsafe-ext` em `yt_dlp/YoutubeDL.py`;
- C3 repetiu buscas por `validate_options` e `allow-unsafe-ext` no mesmo arquivo.

A saída do CodeScout para essa instância registrou 10 alvos identificados,
7 analisados e 7 mantidos, com duração de 210,2 s. A versão C2 removeu
`Implementation Suggestions`; a auditoria registrou `c2_contains_code = False`.
O tempo do CodeScout é compartilhado por C2 e C3, pois ambas derivam da mesma
execução.

**Interpretação provisória:** a contextualização alterou o padrão de exploração
observado entre as condições, mas nenhuma delas chegou à geração de patch. Esses
dados não permitem concluir que C2/C3 melhoram a resolução. A repetição de buscas
em C2/C3 sugere que o resolvedor identifica termos relevantes, mas não progride
para uma alteração verificável.

### 14.4. Teste exploratório de temperatura 0,3 em C1 (2026-11-04)

Foi realizada uma execução exploratória de C1 com `temperature = 0.3`, em vez do
valor experimental de referência `0.0`.

No trecho de trajetória inspecionado, o resolvedor:
- procurou o código em caminhos inexistentes (`/home/user/bin/yt-dlp_night/yt_dlp/`
  e `/usr/lib/python3.14/site-packages/yt_dlp/`);
- criou manualmente diretórios vazios nesses caminhos após receber erros de
  inexistência;
- repetiu comandos `grep` em caminhos sem o código do projeto;
- executou 42 vezes um comando `echo` que apenas imprimia a mensagem
  “Please check the yt-dlp documentation and source code for the correct way to
  handle unsafe extensions.”.

Resumo informado para essa execução: 50 ações, 8 comandos distintos e 42 ações
repetidas. Não foi produzido patch.

A temperatura 0,3 aumentou a diversidade de comandos em relação ao diagnóstico
anterior de C1 em temperatura 0,0 (2 comandos distintos naquele resumo), mas não
produziu progresso na resolução. Essa comparação é apenas exploratória: não deve
ser usada como comparação controlada de desempenho, pois a temperatura foi
alterada e a execução não gerou solução.

**Decisão provisória:** manter `temperature = 0.0` como configuração comum às
condições do experimento. Não alterar a temperatura apenas em C1. Uma eventual
investigação de temperatura deve ser tratada como experimento separado e
controlado.

### 14.5. Verificação do diretório de trabalho e estado do repositório (2026-11-04)

A inspeção no notebook Kaggle confirmou que o diretório atual do projeto
experimental era `/kaggle/working/gos`. Na raiz estavam os arquivos e diretórios
do `guide-or-solver`, mas não havia uma pasta `yt_dlp/` nesse nível. Isso, por si
só, não comprova erro: o checkout da instância do projeto-alvo pode estar em outro
diretório, definido pelo runner.

O `git status --short` observado naquele momento foi:

```text
 M results/environment.txt
 M results/qwen2.5-coder_7b/yt-dlp__yt-dlp-16919/C1_run0.json
 D results/qwen2.5-coder_7b/yt-dlp__yt-dlp-16919/C2_run0.json
 D results/qwen2.5-coder_7b/yt-dlp__yt-dlp-16919/C3_run0.json
```

As exclusões de `C2_run0.json` e `C3_run0.json` e as alterações locais precisam
ser reconciliadas conscientemente antes de operações Git de commit/push. Não
descartar nem sobrescrever esses arquivos sem verificar se as exclusões foram
intencionais.

**Diagnóstico pendente:** inspecionar `runner/run_condition.py` e os módulos de
`runner/` e `common/` que preparam o checkout, para confirmar o `cwd` efetivo
passado a `LocalEnvironment` e o caminho em que a instância `yt-dlp` é clonada.
A ausência de `yt_dlp/` na raiz de `/kaggle/working/gos` não basta para concluir
que o resolvedor foi iniciado no diretório errado.

### 14.6. Próximas verificações antes de executar o benchmark completo

1. Confirmar no código do runner o diretório de checkout da instância e o `cwd`
   efetivo do `LocalEnvironment`.
2. Inspecionar, na trajetória de C1/C2/C3, os pares comando/observação para
   verificar se a saída dos comandos é entregue ao modelo e se ele consegue
   utilizá-la em passos posteriores.
3. Confirmar que o prompt e a configuração textual orientam o agente a descobrir
   o diretório atual do repositório antes de procurar arquivos em caminhos
   presumidos.
4. Comparar automaticamente C2 e C3, removendo `Implementation Suggestions` de
   C3 e verificando a igualdade do restante.
5. Fazer uma execução curta de diagnóstico, com limite reduzido de ações, antes
   de repetir as três condições completas.
6. Manter temperatura, seed, modelo, limites e demais parâmetros idênticos entre
   C1, C2 e C3 na comparação principal.

Até essas verificações serem concluídas, os resultados descritos nesta seção
devem ser tratados como diagnósticos de piloto, e não como evidência conclusiva
sobre a eficácia da contextualização.

### 14.7. Cronologia dos testes do piloto (2026-11-03 a 2026-11-04)

> Datas inferidas dos carimbos de data dos arquivos de saída; revisar onde indicado.

| Data | Evento |
|---|---|
| `[PREENCHER]` | Piloto 1: Qwen2.5-Coder 7B, configuração original (`default.yaml`, `LitellmModel`, `ollama/`), três condições |
| `[PREENCHER]` | Piloto 2: DeepSeek-Coder-V2 16B, com regras extras nos templates |
| 2026-11-03 | Diagnósticos isolados: versões e configuração, marcador de encerramento, capacidades do Ollama, chamadas diretas ao LiteLLM, agente (`diag.zip`) |
| 2026-11-03 | Testes de agente com a configuração `mini.yaml`, textual e a do pipeline (20:26–20:43) |
| 2026-11-03 | Consolidação das correções em `common/utils.py`, `runner/codescout.py` e `runner/run_condition.py` |
| 2026-11-04 | Teste mínimo do `run_agent` corrigido, nos dois modelos |
| 2026-11-04 | Execuções com o pipeline corrigido (Qwen, `yt-dlp__yt-dlp-16919`): C1 13:19, C2 13:30, C3 depois disso |
| 2026-11-04 | Correção de progresso por passo em `run_condition.py` (ainda sem validação no Kaggle) |

### 14.8. Pilotos 1 e 2 (configuração original): dados e causa real de encerramento

Os dois pilotos usaram `agent_config.json` com `source = .../minisweagent/config/default.yaml` (template
textual) e `status` registrado como `'exit_status'` (bug descrito na Seção 12). O status real foi lido da
mensagem `exit` da trajetória salva.

**Piloto 1 — Qwen2.5-Coder 7B (`ollama/`, `LitellmModel`):**

| Condição | Status real | Ações / chamadas | Tokens (entrada + saída) | Duração | Mensagens | Patch |
|---|---|---:|---:|---:|---:|---|
| C1 | `LimitsExceeded` | 50 / 50 | 1.289.418 + 2.477 | 242,6 s | 103 | Vazio |
| C2 | `LimitsExceeded` | 50 / 50 | 283.400 + 2.089 | 89,0 s | 103 | Vazio |
| C3 | `LimitsExceeded` | 50 / 50 | 265.823 + 1.691 | 72,5 s | 103 | Vazio |

Última observação de cada condição: C1, `THOUGHT:: not found` (código 127: o texto de raciocínio foi usado como
comando); C2, `echo` repetindo o texto da tarefa; C3, `echo 'No changes detected in yt_dlp directory.'`.
Nenhum erro de formato: todas as 50 respostas viraram comandos.

**Piloto 2 — DeepSeek-Coder-V2 16B (`ollama/`, regras extras nos templates):**

| Condição | Status real | Ações / chamadas (registradas) | Tokens | Duração | Mensagens | Patch |
|---|---|---:|---:|---:|---:|---|
| C1 | `RepeatedFormatError` | 1 / 1 | 5.607 + 127 | 67,9 s | 8 | Vazio |
| C2 | `RepeatedFormatError` | 1 / 1 | 1.942 + 53 | 12,9 s | 8 | Vazio |
| C3 | `RepeatedFormatError` | 1 / 1 | 2.033 + 53 | 6,6 s | 8 | Vazio |

Estrutura das mensagens: `system, user, assistant, tool, user, user, user, exit`; a última mensagem de usuário
diz que nenhuma chamada de ferramenta foi encontrada na resposta. Ou seja, o modelo respondeu a primeira vez, e
depois três respostas foram rejeitadas pelo parser. `llm_calls = 1` subestima as consultas reais (≥ 4).

Outras métricas desses pilotos: CodeBLEU `NaN` (patches vazios), volatilidade do agente 0, `applied` não deve ser
lido como "patch aplicado" quando o patch é vazio (`apply_patch` devolve `True` para patch vazio).

**Descarte:** os resultados dos pilotos 1 e 2 são **inválidos como medida de desempenho** (status lido
incorretamente, configuração incoerente, contadores subestimados) e foram movidos para
`results_pilotos_descartados/`. Servem apenas como registro do diagnóstico.

### 14.9. Diagnósticos isolados e seus resultados

"Confirmado" = observado diretamente; "Hipótese" = interpretação ainda sem teste que a isole.

| # | Teste | Resultado | Situação |
|---:|---|---|---|
| 1 | Versões e configuração carregada | mini-swe-agent 2.4.6, litellm 1.93.2. `default_agent_config()` carregava `default.yaml` (template textual: bloco `mswea_bash_command`, `THOUGHT`) enquanto o modelo era `LitellmModel`, que lê `tool_calls` | Confirmado (configuração) |
| 2 | Encerramento (`LocalEnvironment`) | `Submitted` só quando o marcador `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` está na **primeira linha** da saída e o código de retorno é 0. `echo MARCADOR` e `echo MARCADOR && outro` encerram; `echo oi && echo MARCADOR` e `echo MARCADOR; false` não | Confirmado |
| 3 | Capacidades no Ollama | Qwen: completion, tools, insert. DeepSeek: completion, insert, template sem `.Tools`. Com `ollama_chat/`, o envio de `tools` ao DeepSeek gera erro HTTP do servidor | Confirmado |
| 4 | LiteLLM direto, `ollama/`, Qwen (5 passos) | Chamadas estruturadas, mas repetiu `pwd && ls && echo 'DONE'` nos 5 passos e nunca respondeu em texto | Confirmado (comportamento); causa não isolada |
| 5 | LiteLLM direto, `ollama/`, DeepSeek | `pwd`, `ls` e depois uma "ferramenta" chamada `DONE` com `{}`, repetida. Nome de ferramenta inexistente | Confirmado; o mecanismo que produz `tool_calls` para um modelo sem tools não foi identificado (o provider `ollama/` do LiteLLM não lista `tools` entre os parâmetros suportados e só liga `format=json` via `response_format`) |
| 6 | LiteLLM direto, `ollama_chat/`, Qwen | Devolve o JSON da chamada como **texto** (`{"name":"bash",...}` em duas linhas e `DONE`), sem `tool_calls` | Confirmado |
| 7 | Agente, `mini.yaml` + `LitellmModel` + `ollama/`, tarefa mínima (Qwen) | `ls -la`, `cat a.txt`, `echo MARCADOR` → `Submitted` (102,9 s). Um turno com ferramenta inválida (`Unknown tool 'echo'`), seguido de recuperação | Confirmado |
| 8 | Agente com a configuração do pipeline (`default.yaml` textual + `LitellmModel` + `ollama/`), tarefa mínima (Qwen) | `ls -la`, `cat a.txt`, `echo MARCADOR` → `Submitted`, sem `THOUGHT` no comando. O desencontro de template, **sozinho**, não reproduz a falha na tarefa mínima | Confirmado. Efeito do desencontro na issue real: hipótese |
| 9 | Agente textual (`mini_textbased.yaml` + `LitellmTextbasedModel` + `ollama_chat/`), tarefa mínima | Qwen (3,4 s) e DeepSeek (42,0 s): 2 turnos, observação entregue e usada, `Submitted` | Confirmado |
| 10 | Testes de agente com `--modo minimo`/`default` (4 execuções) | Abortaram na primeira chamada por `Cost must be > 0.0`; nenhuma mensagem do assistente | Inválidos (corrigido com `cost_tracking`) |
| 11 | `num_ctx` | `ollama ps` mostra `context_length = 32768` nos dois modelos **quando a opção é enviada direto** ao `/api/chat` (é o caso do CodeScout). O repasse pelo LiteLLM no resolvedor **não foi testado** | Pendente (14.13) |
| 12 | Teste mínimo do `run_agent` corrigido (`ollama_chat/` textual) | Qwen: `Submitted`, 1 ação, 2 chamadas, 0 erros, `usage_source = litellm.completion`, 1.581 + 104 tokens, 101,4 s. DeepSeek: `Submitted`, 1 ação, 2 chamadas, 0 erros, 1.796 + 136 tokens, 42,7 s | Confirmado |

### 14.10. Alterações de código aplicadas (consolidação de 2026-11-03)

- **`common/utils.py`:** `WORK` em `/tmp/gos_work` (variável `GOS_WORK`); `.git/info/exclude` no checkout
  (`.venv`, `__pycache__`, `*.egg-info`, `.pytest_cache` etc.); `git checkout` verificado; `run()` devolve código
  124 em timeout em vez de levantar exceção; `run_tests` não executa a suíte inteira quando não há arquivos de
  teste; `new_files_in` (arquivos criados pelo agente) e `audit_leak`.
- **`runner/codescout.py`:** até 3 tentativas por chamada ao Ollama; cada chamada registra `done_reason` e
  `near_ctx_limit`; o resultado inclui `any_truncated`.
- **`runner/run_condition.py`:** `LitellmTextbasedModel` com `ollama_chat/` e a seção `model` do
  `mini_textbased.yaml`; `exit_status`/`submission` lidos do dict; contagem de chamadas e tokens por
  interceptação de `litellm.completion`; `actions` = observações com `<returncode>`; resultado com
  `provenance` (commit, hash da configuração, versões), `leak_audit`, `patch_nonempty`, `new_files`,
  `venv_ok`; portão de validade do CodeScout (C2 sem sugestões, sem código residual, sem truncamento) e pulo
  registrado em `*.skipped.json`; `agent_config.json` regravado a cada execução.
- **Progresso por passo (2026-11-04, sem validação no Kaggle):** linha por comando e por chamada ao modelo e
  `logs/<modelo>_<instância>_<condição>_run<k>.steps.jsonl`; desliga com `GOS_PROGRESS=0`.

Observação: os `codescout.json` gerados antes desta consolidação não têm `any_truncated` (valor `None`).

### 14.11. Piloto com o pipeline corrigido: métricas de degeneração (Qwen, `yt-dlp__yt-dlp-16919`)

Complementa a tabela de 14.3 com a contagem de comandos distintos (calculada sobre as 50 ações de cada execução):

| Condição | Comandos distintos | Mais repetidos |
|---|---:|---|
| C1 | 2 | `man yt-dlp` (25×) e `sudo apt-get install man-db` (25×) |
| C2 | 9 | dois `grep -n "allow-unsafe-ext" yt_dlp/YoutubeDL.py` (22× e 21×) |
| C3 | `[PREENCHER]` | `[PREENCHER]` (14.3 cita `validate_options` e `allow-unsafe-ext`) |

Em todas, `llm_errors = 0`, `usage_source = litellm.completion`, `n_non_observation_msgs = 0` (nenhuma resposta
rejeitada por formato), `venv_ok = True`, `leak_audit = []`. C1 permaneceu em um ciclo de dois comandos sem
inspecionar o código; C2 chegou ao arquivo da área da issue, mas passou 43 das 50 ações em duas variantes da
mesma busca. Com uma execução por condição e um único modelo, isso é indício descritivo, não efeito.
Registrar a métrica de degeneração (fração de ações repetidas, maior sequência idêntica) para todas as
execuções.

### 14.12. Respostas às verificações pendentes de 14.5 e 14.6

- **Checkout e `cwd` (14.6, item 1):** na versão usada nos pilotos, `fresh_checkout(inst, WORK / instance_id)`
  com `WORK = <raiz>/work`, e `LocalEnvironment(cwd=str(workdir))`; portanto o agente iniciava no diretório do
  projeto-alvo (`/kaggle/working/gos/work/yt-dlp__yt-dlp-16919`), e não na raiz do repositório de pesquisa. Os
  caminhos inexistentes tentados no teste de 0,3 (14.4) vêm do modelo supor caminhos em vez de inspecionar o
  diretório atual, e não de um `cwd` errado. Agora o checkout fica em `/tmp/gos_work`.
- **Estado do Git (14.5):** as exclusões de `C2_run0.json`/`C3_run0.json` e a alteração de `C1_run0.json`
  correspondem à limpeza dos pilotos antigos (arquivos movidos para `results_pilotos_descartados/`) e à
  regravação da C1 com o pipeline corrigido. Confirmar no histórico antes do commit; as exclusões eram
  intencionais.
- **Observações sobre o prompt (14.6, item 3):** os testes de 14.9 indicam que o modelo recebe e usa a observação
  de cada comando (testes 7–9), então o problema na issue real não é a entrega das observações.

### 14.13. Pendências para retomar (ordem sugerida)

1. Rodar o DeepSeek (C1, C2, C3) na instância-piloto com o pipeline corrigido, lendo os primeiros turnos de cada
   execução.
2. Conferir, em uma execução com erros de formato, se `llm_calls` fica maior que `n_assistant_msgs`
   (valida a contagem por interceptação).
3. Testar se o `num_ctx` chega ao Ollama pelo LiteLLM: descarregar o modelo, chamar `litellm.completion` com
   `num_ctx = 32768` e consultar `/api/ps`.
4. Comparar C2 e C3 automaticamente (14.2), removendo `Implementation Suggestions` de C3.
5. Calcular a degeneração para todas as execuções e decidir as **métricas primárias** antes do corpus completo.
6. Decidir, como regra de protocolo (não como ajuste silencioso), como tratar execuções degeneradas: aceitar e
   relatar; registrar como métrica; ou rodar uma variante com regras anti-repetição, idêntica nas três
   condições. A temperatura permanece 0.0.
7. Separar uma issue de calibração, diferente das instâncias de avaliação, para qualquer ajuste de pipeline.
8. Definir a política para arquivos novos criados pelo agente (scripts de reprodução), hoje em `new_files`.
9. Atualizar `.gitignore` (`work/`, `logs/`, `results_pilotos_descartados/`) e reconciliar o `git status`.
10. Enviar a versão de `run_condition.py` com progresso por passo e validá-la no Kaggle.
11. Decidir se o `codescout.json` do piloto será regenerado (para ter `any_truncated`); isso exige refazer C2 e
    C3.

### 14.14. Nota de verificação sobre 14.3

`[REVISAR]` A seção 14.3 afirma que um teste isolado com `DefaultAgent` e `LitellmTextbasedModel` repetiu
comandos `ls` após receber a saída. Os registros desta etapa mostram a repetição de `pwd && ls` nas chamadas
**diretas ao LiteLLM** com `ollama/` (14.9, teste 4), e que os testes com `DefaultAgent` em modo textual na
tarefa mínima terminaram em dois turnos com `Submitted` nos dois modelos (14.9, testes 9 e 12). Confirmar a
qual teste a afirmação se refere antes de citá-la no artigo. O texto de 14.3 foi mantido sem alteração.
