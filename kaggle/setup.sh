#!/usr/bin/env bash
# Prepara um notebook Kaggle (GPU T4, Internet ativada) para o experimento.
set -euo pipefail
cd "$(dirname "$0")/.."

MODELS=$(python -c "import yaml;print(' '.join(m['name'].split('/',1)[1] for m in yaml.safe_load(open('config/experiment.yaml'))['models']))")

command -v ollama >/dev/null || (curl -fsSL https://ollama.com/install.sh | sh)
pgrep -x ollama >/dev/null || (OLLAMA_KEEP_ALIVE=-1 setsid nohup ollama serve > ollama.log 2>&1 &)
sleep 5
for M in $MODELS; do ollama pull "$M"; done

pip install -q -r requirements.txt pytest-json-report

mkdir -p results
{
  echo "date: $(date -u)"
  echo "ollama: $(ollama --version)"
  ollama list
  for M in $MODELS; do echo "== $M"; ollama show "$M"; done
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
  lscpu | grep -E 'Model name|^CPU\(s\)'
  free -h | head -2
  cat /etc/os-release | head -2
  python --version
  pip freeze | grep -Ei 'mini-swe-agent|litellm|codebleu'
} > results/environment.txt 2>&1
cat results/environment.txt
