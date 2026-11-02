#!/usr/bin/env bash
# Prepara um notebook Kaggle (GPU T4, Internet ativada) para o experimento.
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL=$(python -c "import yaml;print(yaml.safe_load(open('config/experiment.yaml'))['model']['name'].split('/',1)[1])")

command -v ollama >/dev/null || (curl -fsSL https://ollama.com/install.sh | sh)
nohup ollama serve > ollama.log 2>&1 &
sleep 5
ollama pull "$MODEL"

pip install -q -r requirements.txt pytest-json-report

mkdir -p results
{
  echo "date: $(date -u)"
  echo "ollama: $(ollama --version)"
  ollama show "$MODEL"
  ollama list | grep "${MODEL%%:*}"
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
  lscpu | grep -E 'Model name|^CPU\(s\)'
  free -h | head -2
  cat /etc/os-release | head -2
  python --version
  pip freeze | grep -Ei 'mini-swe-agent|litellm|codebleu'
} > results/environment.txt 2>&1
cat results/environment.txt
