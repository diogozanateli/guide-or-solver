"""Utilitários compartilhados: configuração, JSONL, git e execução de testes."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
# FORA do repositório: o agente roda sem sandbox e, com WORK dentro de ROOT, um simples
# "cd ../.." chegaria a data/ (patch humano, FAIL_TO_PASS) e results/ (outras condições).
WORK = Path(os.environ.get("GOS_WORK", "/tmp/gos_work"))

# Artefatos de ambiente/trabalho que nunca devem entrar no patch do agente.
GIT_EXCLUDES = [".venv/", ".report.json", ".tmp.patch", "__pycache__/", "*.pyc",
                ".pytest_cache/", "*.egg-info/", ".mypy_cache/", ".ruff_cache/"]

# Indícios de que o agente foi procurar o gabarito ou arquivos do projeto de pesquisa.
LEAK_PATTERNS = [r"/kaggle", r"gos/(?:data|results|config)", r"instances[\w.-]*\.jsonl",
                 r"code_patch|test_patch|FAIL_TO_PASS|PASS_TO_PASS"]
_LEAK_RE = re.compile("|".join(LEAK_PATTERNS))


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text())


def model_slug(name: str) -> str:
    """'ollama/qwen2.5-coder:7b' -> 'qwen2.5-coder_7b' (nome de pasta)."""
    return name.split("/", 1)[-1].replace(":", "_").replace("/", "_")


def selected_model() -> dict:
    """Modelo escolhido via --model (nome completo, slug ou nome sem 'ollama/').
    Sem --model, usa o primeiro da lista em config/experiment.yaml."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--model")
    arg = ap.parse_known_args()[0].model
    models = load_config()["models"]
    if not arg:
        return models[0]
    for m in models:
        if arg in (m["name"], model_slug(m["name"]), m["name"].split("/", 1)[-1]):
            return m
    raise SystemExit(f"Modelo '{arg}' não está em config/experiment.yaml: "
                     f"{[m['name'] for m in models]}")


def model_results_dir() -> Path:
    """results/<slug-do-modelo>/ — um diretório por modelo."""
    d = RESULTS / model_slug(selected_model()["name"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def run(cmd: str, cwd: Path | None = None, timeout: int = 900) -> subprocess.CompletedProcess:
    """Executa um comando. Timeout NÃO levanta exceção: devolve returncode 124."""
    try:
        return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        txt = lambda x: x.decode(errors="ignore") if isinstance(x, bytes) else (x or "")
        return subprocess.CompletedProcess(cmd, 124, txt(e.stdout),
                                           txt(e.stderr) + f"\n[timeout após {timeout}s]")


def split_patch(diff: str) -> tuple[str, str]:
    """Separa um diff unificado em (patch_de_codigo, patch_de_teste)."""
    code, test, current, is_test = [], [], [], False
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git"):
            if current:
                (test if is_test else code).extend(current)
            current = []
            path = line.split(" b/")[-1].strip()
            is_test = is_test_path(path)
        current.append(line)
    if current:
        (test if is_test else code).extend(current)
    return "".join(code), "".join(test)


def is_test_path(path: str) -> bool:
    p = path.lower()
    name = p.rsplit("/", 1)[-1]
    return ("/tests/" in f"/{p}" or "/test/" in f"/{p}"
            or name.startswith("test_") or name.endswith("_test.py")
            or name == "conftest.py")


def patch_files(diff: str) -> list[str]:
    return [l.split(" b/")[-1].strip() for l in diff.splitlines()
            if l.startswith("diff --git")]


def new_files_in(diff: str) -> list[str]:
    """Arquivos CRIADOS pelo patch (ex.: scripts de reprodução do agente)."""
    out, cur = [], None
    for l in diff.splitlines():
        if l.startswith("diff --git"):
            cur = l.split(" b/")[-1].strip()
        elif l.startswith("new file mode") and cur:
            out.append(cur)
    return out


def _write_excludes(repo: Path) -> None:
    p = repo / ".git" / "info" / "exclude"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(GIT_EXCLUDES) + "\n")


def fresh_checkout(inst: dict, dest: Path) -> Path:
    """Clona o repositório na revisão base, sem histórico futuro (evita vazamento)."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{inst['repo']}.git"
    for cmd in (f"git init -q {dest}", f"git remote add origin {url}"):
        r = run(cmd, cwd=dest if dest.exists() else None)
        if r.returncode != 0:
            raise RuntimeError(f"{cmd}: {r.stderr}")
    r = run(f"git fetch -q --depth 1 origin {inst['base_commit']}", cwd=dest)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    r = run("git checkout -q FETCH_HEAD", cwd=dest)
    if r.returncode != 0:
        raise RuntimeError(f"git checkout falhou: {r.stderr}")
    run("git remote remove origin", cwd=dest)
    _write_excludes(dest)
    return dest


def setup_venv(repo_dir: Path, timeout: int = 900) -> bool:
    """Cria .venv com uv e instala o projeto e o pytest. False em qualquer falha/timeout."""
    cmds = [
        "uv venv -q .venv",
        "uv pip install -q --python .venv/bin/python -e '.[test]' "
        "|| uv pip install -q --python .venv/bin/python -e '.[tests]' "
        "|| uv pip install -q --python .venv/bin/python -e .",
        "test -f requirements-dev.txt && uv pip install -q --python .venv/bin/python "
        "-r requirements-dev.txt || true",
        "test -f requirements/tests.txt && uv pip install -q --python .venv/bin/python "
        "-r requirements/tests.txt || true",
        "uv pip install -q --python .venv/bin/python pytest pytest-json-report",
    ]
    for c in cmds:
        if run(c, cwd=repo_dir, timeout=timeout).returncode != 0:
            return False
    return True


def apply_patch(repo_dir: Path, diff: str) -> bool:
    """True = sem conflito. ATENÇÃO: patch vazio também devolve True; use patch_nonempty."""
    if not diff.strip():
        return True
    p = repo_dir / ".tmp.patch"
    p.write_text(diff)
    r = run("git apply --whitespace=nowarn .tmp.patch", cwd=repo_dir)
    p.unlink()
    return r.returncode == 0


def run_tests(repo_dir: Path, test_files: list[str], timeout: int = 900) -> dict[str, str]:
    """Roda pytest e devolve {nodeid: outcome}. Sem arquivos de teste existentes: {}
    (antes isso rodava a suíte inteira do repositório)."""
    report = repo_dir / ".report.json"
    files = " ".join(f for f in test_files if (repo_dir / f).exists())
    if not files:
        return {}
    run(f".venv/bin/python -m pytest -q -p no:cacheprovider --json-report "
        f"--json-report-file={report.name} {files}", cwd=repo_dir, timeout=timeout)
    if not report.exists():
        return {}
    data = json.loads(report.read_text())
    report.unlink()
    return {t["nodeid"]: t["outcome"] for t in data.get("tests", [])}


def git_diff(repo_dir: Path) -> str:
    excl = " ".join(f"':(exclude){e.rstrip('/')}'" for e in (".venv/", ".report.json", ".tmp.patch"))
    run("git add -A", cwd=repo_dir)
    return run(f"git diff --cached -- . {excl}", cwd=repo_dir).stdout


def audit_leak(messages: list[dict]) -> list[dict]:
    """Procura, nos turnos do agente (a partir da 3ª mensagem), acessos a caminhos do
    projeto de pesquisa ou a nomes de campos do gabarito. Lista vazia = nenhum indício."""
    hits = []
    for i, m in enumerate(messages):
        if i < 2:  # system e instância (contêm só templates + issue)
            continue
        txt = json.dumps(m, ensure_ascii=False, default=str)
        for mt in _LEAK_RE.finditer(txt):
            hits.append({"msg": i, "role": m.get("role"), "match": mt.group(0),
                         "context": txt[max(0, mt.start() - 80): mt.end() + 80]})
    return hits[:20]
