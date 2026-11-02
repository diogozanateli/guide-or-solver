# Guide or Solver? — Pacote de Replicação

Experimento que compara um agente de LLM como **resolvedor autônomo** (C1) e como
**contextualizador** que orienta o resolvedor, sem código (C2) ou com proposta de
implementação (C3), em *issues* reais de projetos Python *open-source*.

## Estrutura

```
DIARIO_EXPERIMENTO.md    # registro de decisões, ambiente e resultados (para a escrita)
scripts/update_diary.py  # preenche os blocos AUTO do diário a partir de data/ e results/
config/experiment.yaml   # TODOS os parâmetros fixados antes da coleta
prompts/                 # prompts versionados (solver e contextualizadores)
common/                  # utilitários compartilhados (config, git, testes)
mining/01_mine.py        # minera issues fechadas por PR mesclado
mining/02_validate.py    # valida FAIL_TO_PASS / PASS_TO_PASS
runner/run_condition.py  # executa C1, C2, C3 (Kaggle, GPU)
runner/evaluate.py       # aplica patches e roda os testes (CPU)
metrics/rq1.py rq2.py rq3.py stats.py
kaggle/setup.sh          # instala Ollama + dependências no Kaggle
data/                    # candidates.jsonl, instances.jsonl, exclusions.csv
results/                 # trajetórias, patches, orientações, métricas
```

## Fluxo

1. **Mineração** (local/Codespaces, CPU): `python mining/01_mine.py`
   (requer `GITHUB_TOKEN` no ambiente).
2. **Validação** (CPU): `python mining/02_validate.py` → `data/instances.jsonl`
   e `data/exclusions.csv`.
3. **Execução** (Kaggle, GPU): ver seção abaixo.
4. **Avaliação** (CPU): `python runner/evaluate.py`.
5. **Métricas**: `python metrics/rq1.py`, `rq2.py`, `rq3.py`, `stats.py`.

## Kaggle

Em um notebook com GPU (T4) e Internet ativada:

```bash
!git clone https://github.com/<usuario>/guide-or-solver.git
%cd guide-or-solver
!bash kaggle/setup.sh
!python runner/run_condition.py --model qwen2.5-coder:7b --limit 5      # piloto
!python runner/run_condition.py --model deepseek-coder-v2:16b --limit 5
```

Os resultados de cada modelo ficam em `results/<modelo>/`, com checkpoint por
execução. Avaliação e métricas também recebem `--model` (padrão: o primeiro modelo
de `config/experiment.yaml`). Ao fim da sessão, faça `git push` de `results/`.

## Reprodutibilidade

`kaggle/setup.sh` grava em `results/environment.txt` a versão do Ollama, o digest e
a quantização do modelo, GPU, CPU, RAM e SO. Não altere `config/experiment.yaml`
após o piloto ser congelado.
