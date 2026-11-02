# Diário do Experimento — Guide or Solver?

Registro cronológico de decisões, configurações, resultados e incidentes, para
apoiar a escrita das seções de Metodologia, Resultados, Ameaças à Validade e
Disponibilidade de Artefatos. Atualizar a cada etapa; não apagar entradas antigas
(se algo mudar, registrar a mudança com data e motivo).

Legenda: `[PREENCHER]` = pendente · **Artigo:** = onde a informação entra no texto.

---

## 1. Visão geral do desenho

- **Objetivo:** verificar se um agente de LLM é mais eficaz como resolvedor
  autônomo de issues ou como contextualizador que orienta a resolução.
- **Condições** (mesmo agente resolvedor, mesmas instruções-base, mesmos limites):
  - **C1 — Autônomo:** recebe apenas o texto original da issue.
  - **C2 — Orientação descritiva:** contextualizador descreve problema, causa,
    arquivos e funções, **sem código**.
  - **C3 — Orientação com implementação:** como C2, mais proposta de implementação.
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

| Item | Valor |
|---|---|
| Runtime | Ollama 0.40.13 |
| Modelo | `qwen2.5-coder:7b` (pesos abertos, Apache 2.0) |
| Digest (ID Ollama) | `dae161e27b0e` |
| Arquitetura / parâmetros | qwen2 / 7.6B |
| Quantização | Q4_K_M (4.7 GB em disco; 6.6 GB carregado na GPU) |
| Contexto máximo do modelo | 32768 |
| Capacidades reportadas | completion, tools, insert |
| Execução | 100% GPU (verificado com `ollama ps`) |
| Velocidade medida | ~32 tokens/s de geração (prompt curto, T4) |
| Carga inicial | ~94 s na primeira chamada (carregamento do modelo) |
| `OLLAMA_KEEP_ALIVE` | `-1` (mantém o modelo carregado na GPU) |

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

**Data de corte de treinamento do modelo:** `[PREENCHER — confirmar na model card]`.
Período de mineração começa em 2025-01-01 para mitigar contaminação.

---

## 4. Agentes e prompts

**Artigo:** Seção 3.2; diretriz *Report System and Prompt Design*.

| Item | Valor |
|---|---|
| Framework | mini-swe-agent 2.4.6 (apenas bash) |
| Limite de ações — resolvedor | 50 |
| Limite de ações — contextualizador | 30 |
| Timeout por comando | 120 s |
| Critério de encerramento | `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` ou limite de ações |
| Prompts | `prompts/solver.md`, `prompts/contextualizer_desc.md`, `prompts/contextualizer_impl.md` |
| Formato da orientação | JSON: `problem`, `root_cause`, `files`, `functions`, `change_description` (+ `proposed_implementation` em C3) |
| Verificação de "sem código" em C2 | filtro automático por regex (`_contains_code`) |
| Prevenção de vazamento | clone apenas da revisão base (`--depth 1`), sem histórico futuro; o patch humano e os testes FAIL_TO_PASS não são fornecidos ao agente |

Alterações nos prompts após o piloto: `[PREENCHER — data, mudança, motivo]`

---

## 5. Seleção de repositórios

**Artigo:** Seção 3.1 (parágrafo de critérios) e Ameaças (validade externa).

Script: `mining/00_select_repos.py` → `data/repos.csv`.

| Critério | Regra |
|---|---|
| C1 | Linguagem principal Python, ≥ 1.000 estrelas, não fork, não arquivado, atividade desde 2025-01-01 (busca do GitHub ordenada por estrelas; máx. 1.000 resultados) |
| C2 | Tamanho ≤ 200 MB |
| C3 | `pyproject.toml`, `setup.py` ou `setup.cfg` na raiz |
| C4 | Usa pytest (configuração, `conftest.py` ou dependência declarada) |
| C5 | Sem extensões compiladas (.c, .cpp, .pyx, .rs, Cargo.toml, ext_modules) |
| C6 | ≥ 10 PRs mesclados vinculados a issues entre 2025-01-01 e 2026-10-31 |
| Corte | Primeiros 40 aprovados por número de estrelas |

Resultados:

| Item | Valor |
|---|---|
| Data da consulta | `[PREENCHER]` (coluna `queried_at`) |
| Repositórios avaliados (M) | `[PREENCHER]` |
| Excluídos por C2 / C3 / C4 / C5 / C6 | `[PREENCHER]` |
| Selecionados (N) | `[PREENCHER]` |

**Histórico:** uma primeira mineração usou uma lista de 24 repositórios escolhida por
conveniência (26 candidatos). Ela foi **descartada** em favor da seleção reprodutível
acima. Não citar no artigo como resultado; apenas como decisão de desenho, se útil.

---

## 6. Mineração de issues

**Artigo:** Seção 3.2 (Procedimentos).

Script: `mining/01_mine.py` → `data/candidates.jsonl`.

- Período: 2025-01-01 a 2026-10-31 (PRs mesclados).
- Vínculo PR → issue: texto do PR com "fixes/closes/resolves #N".
- Filtros: issue com texto; PR altera código e testes; até 3 arquivos de código
  (`max_code_files`); até 30 candidatos por repositório (`max_candidates_per_repo`).
- Revisão base: primeiro pai do merge commit.

| Item | Valor |
|---|---|
| Data da mineração | `[PREENCHER]` |
| Candidatos minerados | `[PREENCHER]` |
| Candidatos por repositório | `[PREENCHER]` |

---

## 7. Validação das instâncias

**Artigo:** Seção 3.2 e tabela de caracterização do corpus.

Script: `mining/02_validate.py` → `data/instances.jsonl`, `data/exclusions.csv`.

- FAIL_TO_PASS: falham na revisão base com os testes do PR e passam com a correção.
- PASS_TO_PASS: passam nas duas versões.
- 3 execuções por versão; resultados diferentes entre execuções → `testes_instaveis`.

| Motivo de exclusão | Quantidade |
|---|---|
| historico_irrecuperavel | `[PREENCHER]` |
| checkout_falhou | `[PREENCHER]` |
| ambiente_nao_executavel | `[PREENCHER]` |
| test_patch_nao_aplica | `[PREENCHER]` |
| code_patch_nao_aplica | `[PREENCHER]` |
| testes_nao_executam | `[PREENCHER]` |
| testes_instaveis | `[PREENCHER]` |
| sem_fail_to_pass | `[PREENCHER]` |
| **Instâncias válidas (corpus final)** | `[PREENCHER]` |

Caracterização do corpus (para tabela no artigo): `[PREENCHER — nº de projetos,
instâncias por projeto, média de arquivos/linhas alteradas no patch humano,
nº médio de testes FAIL_TO_PASS e PASS_TO_PASS]`

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

Falhas de execução (timeouts, erros do agente, sessões interrompidas):
`[PREENCHER]`

Violações da regra "sem código" em C2 (`_contains_code = True`): `[PREENCHER —
quantidade e tratamento]`

---

## 10. Resultados

Arquivos: `results/rq1_summary.csv`, `rq2_summary.csv`, `rq3_summary.csv`, `stats.csv`.

### RQ1 — Resolução e eficiência

| Condição | Taxa de resolução | Ações (média) | Tokens resolvedor | Tokens contextualizador | Tokens total | Duração (s) |
|---|---|---|---|---|---|---|
| C1 | | | | — | | |
| C2 | | | | | | |
| C3 | | | | | | |

McNemar (com correção de Holm): C1×C2 `[p]` · C1×C3 `[p]` · C2×C3 `[p]`

### RQ2 — Localização

| Condição | Nível | Precisão | Revocação | F1 | Acerto exato |
|---|---|---|---|---|---|
| C2 | arquivo | | | | |
| C2 | função | | | | |
| C3 | arquivo | | | | |
| C3 | função | | | | |

### RQ3 — Relação com a correção humana

| Condição | CodeBLEU | Volatilidade agente | Volatilidade humano |
|---|---|---|---|
| C1 | | | |
| C2 | | | |
| C3 | | | |

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
- **Modelo único de 7B quantizado:** resultados podem não valer para modelos maiores
  ou proprietários.
- **Seleção de repositórios:** favorece projetos Python populares, maduros e sem
  código nativo.
- **Testes como oráculo:** patches podem passar nos testes sem estarem corretos
  (validação humana `[PREENCHER — se for feita]`).
- **CodeBLEU:** similaridade com a referência não implica equivalência funcional.
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
