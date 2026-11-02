"""Utilitários compartilhados: configuração, JSONL, git e execução de testes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
WORK = ROOT / "work"


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
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)


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


def fresh_checkout(inst: dict, dest: Path) -> Path:
    """Clona o repositório na revisão base, sem histórico futuro (evita vazamento)."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{inst['repo']}.git"
    run(f"git init -q {dest}")
    run(f"git remote add origin {url}", cwd=dest)
    r = run(f"git fetch -q --depth 1 origin {inst['base_commit']}", cwd=dest)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    run("git checkout -q FETCH_HEAD", cwd=dest)
    run("git remote remove origin", cwd=dest)
    return dest


def setup_venv(repo_dir: Path, timeout: int = 900) -> bool:
    """Cria .venv com uv e instala o projeto e o pytest."""
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
    if not diff.strip():
        return True
    p = repo_dir / ".tmp.patch"
    p.write_text(diff)
    r = run("git apply --whitespace=nowarn .tmp.patch", cwd=repo_dir)
    p.unlink()
    return r.returncode == 0


def run_tests(repo_dir: Path, test_files: list[str], timeout: int = 900) -> dict[str, str]:
    """Roda pytest e devolve {nodeid: outcome}."""
    report = repo_dir / ".report.json"
    files = " ".join(f for f in test_files if (repo_dir / f).exists())
    run(f".venv/bin/python -m pytest -q -p no:cacheprovider --json-report "
        f"--json-report-file={report.name} {files}", cwd=repo_dir, timeout=timeout)
    if not report.exists():
        return {}
    data = json.loads(report.read_text())
    report.unlink()
    return {t["nodeid"]: t["outcome"] for t in data.get("tests", [])}


def git_diff(repo_dir: Path) -> str:
    excl = "':(exclude).venv' ':(exclude).report.json'"
    run("git add -A", cwd=repo_dir)
    return run(f"git diff --cached -- . {excl}", cwd=repo_dir).stdout
